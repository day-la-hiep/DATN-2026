"""Nghiệp vụ sách giáo khoa (pipeline `book_ingest`): dữ liệu sách cho API admin (danh sách, chi tiết + trạng thái bước, tạo/xoá, ảnh
trang, mục lục, chunk), cài đặt (`books.profile`), các bước đang chạy trong process, và lưu chunk vào Qdrant (bước "Lưu vào kho tri thức"): mỗi chunk của `chunks.jsonl` -> một point
(vector = embedding của `context_text`, payload = metadata mục lục + trang + vị trí PDF nguồn trong MinIO).

Collection `settings.QDRANT_BOOK_COLLECTION`, cosine, cùng embedding local như KB guideline. Xây trên capability Qdrant generic (đồng bộ) của
`QdrantVectorClient` vì pipeline chạy ở thread nền riêng. Nạp lại một sách luôn xoá các point cũ của sách đó trước (lọc theo `book_id`) nên
chunk bị xoá/đổi sau khi chỉnh mục lục không còn sót lại. Embedding do pipeline tính, service này chỉ lưu/xoá/đếm."""
import asyncio
import json
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic.alias_generators import to_camel
from qdrant_client.models import PointStruct

from app.dto.toc_pipeline import TocBookOutput, TocBookSummary, TocListOutput, TocProgress, TocSettings, TocStageOutput, TocUpdate
from app.exception.errors import ConflictError, InvalidError, NotFoundError
from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.models.book_profile import Profile
from app.models.book_stage import STAGE_BY_ID, STAGES
from app.repositories.book_repository import BOOK_ID_RE, BookRecord, BookRepository, now_iso
from pipeline.book_ingest.profile import ProfileError, default_profile, profile_from_dict
from pipeline.book_ingest.textutil import sha, slugify

_PAYLOAD_KEYS = ("chunk_id", "seq", "book_id", "text", "context_text", "part", "section", "topic", "subtopic", "toc_path", "toc_node_ids",
                 "level", "pages_hint", "boundary", "suspect", "page_start", "page_end", "page_printed_start", "page_printed_end",
                 "tokens", "chars")

_PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 500 * 1024 * 1024
PAGE_IMAGE_DPI = 80
PAGE_IMAGE_KEY = "page_img/p{page}.png"


def camelize(obj: Any) -> Any:
    """Đổi key dict snake_case -> camelCase đệ quy (record của pipeline là snake_case)."""
    if isinstance(obj, dict):
        return {
            (to_camel(k) if isinstance(k, str) and "_" in k else k): camelize(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [camelize(v) for v in obj]
    return obj


def _paginate(
    rows: list[dict[str, Any]], page: int, page_size: int
) -> list[dict[str, Any]]:
    start = (max(page, 1) - 1) * page_size
    return rows[start : start + page_size]


def temp_root() -> Path:
    """Thư mục tạm cho công cụ cần file thật (bản sao PDF để pdftotext/Docling/pdftoppm đọc)."""
    p = Path(tempfile.gettempdir()) / "book_ingest_tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


class BookService:
    def __init__(self, repository: BookRepository, qdrant: QdrantVectorClient, collection: str) -> None:
        """`repository` = bản ghi sách trên bucket sách (`files` của nó dùng cho dữ liệu sách + cache LLM, tạo bucket nếu chưa có); `collection` chứa chunk đã lưu vào kho
        tri thức."""
        self._repo, self.files = repository, repository.files
        self._qdrant, self.collection = qdrant, collection
        self.files.ensure_bucket()
        # (book_id, stage_id) -> cờ dừng của lần chạy đang diễn ra trong process này (instance dùng chung cả process, xem deps.py)
        self._runs: dict[tuple[str, str], threading.Event] = {}
        self._runs_lock = threading.Lock()

    # ---- tiện ích trên repository một sách ----
    @staticmethod
    def read_profile(store: BookRecord) -> Profile:
        """Đọc cài đặt của sách (`books.profile`); thiếu hoặc sai thì báo lỗi hiển thị cho người dùng."""
        data = store.profile_data()
        if data is None:
            raise InvalidError("Cài đặt của sách bị lỗi: sách chưa có cài đặt")
        try:
            return profile_from_dict(data, store.book_id)
        except ProfileError as exc:
            raise InvalidError(f"Cài đặt của sách bị lỗi: {exc}") from exc

    @staticmethod
    def save_profile(store: BookRecord, profile: Profile) -> None:
        store.set_profile_data(profile.model_dump(mode="json"))

    @staticmethod
    def blocking_deps(store: BookRecord, stage_id: str, stages: dict[str, Any] | None = None) -> list[str]:
        """Các bước phụ thuộc CHƯA approved (rỗng = được phép chạy). Truyền `stages` (từ `store.status()`) để khỏi đọc lại."""
        st = stages if stages is not None else store.status()["stages"]
        return [d for d in STAGE_BY_ID[stage_id]["deps"] if st[d].get("state") != "approved"]

    @staticmethod
    def running_stages(store: BookRecord) -> list[str]:
        return [sid for sid, s in store.status()["stages"].items() if s.get("state") == "running"]

    @staticmethod
    def local_pdf(store: BookRecord) -> Path:
        """Bản sao tạm của `source.pdf` trên đĩa (tải một lần, dùng lại khi cùng kích thước). Bị xoá cùng sách."""
        try:
            return store.files.local_copy("source.pdf", temp_root() / store.book_id / "source.pdf")
        except FileNotFoundError as exc:
            raise FileNotFoundError("Không tìm thấy file PDF của sách.") from exc

    # ---- bước đang chạy trong process ----
    def track_run(self, book_id: str, stage_id: str) -> threading.Event:
        cancel = threading.Event()
        with self._runs_lock:
            self._runs[(book_id, stage_id)] = cancel
        return cancel

    def untrack_run(self, book_id: str, stage_id: str) -> None:
        with self._runs_lock:
            self._runs.pop((book_id, stage_id), None)

    def run_cancel_event(self, book_id: str, stage_id: str) -> threading.Event | None:
        with self._runs_lock:
            return self._runs.get((book_id, stage_id))

    # ---- sách ----
    def ensure_idle(self, store: BookRecord, action: str) -> None:
        self.reconcile(store)
        if self.running_stages(store):
            raise ConflictError(f"Sách đang được xử lý — hãy chờ xong hoặc dừng trước khi {action}.")

    def reconcile(self, store: BookRecord) -> None:
        """Bước ghi `running` nhưng không có thread nào đang chạy nó (Core vừa khởi động lại, thread chết) -> failed."""
        for sid, st in store.status()["stages"].items():
            with self._runs_lock:
                active = (store.book_id, sid) in self._runs
            if st.get("state") == "running" and not active:
                store.update_stage(
                    sid,
                    state="failed",
                    finished_at=now_iso(),
                    error="Tiến trình xử lý đã dừng bất thường (xem nhật ký).",
                )

    def _stage_outputs(self, store: BookRecord) -> list[TocStageOutput]:
        status = store.status()["stages"]
        out = []
        for s in STAGES:
            st = status[s["id"]]
            prog = st.get("progress")
            out.append(
                TocStageOutput(
                    id=s["id"],
                    title=s["title"],
                    deps=s["deps"],
                    uses_llm=s["llm"],
                    state=st.get("state", "not_started"),
                    started_at=st.get("started_at"),
                    finished_at=st.get("finished_at"),
                    approved_at=st.get("approved_at"),
                    progress=TocProgress(**prog)
                    if isinstance(prog, dict)
                    else None,
                    summary=camelize(st.get("summary"))
                    if st.get("summary")
                    else None,
                    error=st.get("error"),
                    options=st.get("options") or {},
                    blocked_by=self.blocking_deps(store, s["id"], status),
                )
            )
        return out

    def list_books(self) -> list[TocBookSummary]:
        out = []
        for bid in self._repo.list_ids():
            store = self._repo.book(bid)
            self.reconcile(store)
            meta = store.meta()
            out.append(
                TocBookSummary(
                    id=bid,
                    title=meta.get("title", bid),
                    created_at=meta.get("created_at"),
                    states={
                        k: v.get("state", "not_started")
                        for k, v in store.status()["stages"].items()
                    },
                )
            )
        return out

    def pdf_pages(self, store: BookRecord) -> int | None:
        cached = store.meta().get("pdf_pages")
        if cached:
            return int(cached)
        try:
            from pypdf import PdfReader

            n = len(PdfReader(str(self.local_pdf(store))).pages)
        except Exception:
            return None
        store.update_meta(pdf_pages=n)
        return n

    def get_book(self, book_id: str) -> TocBookOutput:
        store = self._repo.open(book_id)
        self.reconcile(store)
        meta = store.meta()
        stages = self._stage_outputs(store)
        return TocBookOutput(
            id=book_id,
            title=meta.get("title", book_id),
            created_at=meta.get("created_at"),
            has_pdf=store.files.exists("source.pdf"),
            pdf_pages=self.pdf_pages(store)
            if store.files.exists("source.pdf")
            else None,
            stages=stages,
            running_stage=next(
                (s.id for s in stages if s.state == "running"), None
            ),
        )

    async def create_book(
        self,
        upload: UploadFile,
        title: str,
        book_id: str | None,
        engine: str | None,
    ) -> TocBookOutput:
        title = title.strip()
        if not title:
            raise InvalidError("Vui lòng nhập tên sách.")
        explicit = (book_id or "").strip()
        bid = explicit or slugify(title).replace("_", "-")[:48]
        if not BOOK_ID_RE.match(bid):
            raise InvalidError(
                "Mã nhận diện chỉ gồm chữ thường a-z, số 0-9, dấu '-' và '_' (2–64 ký tự)."
            )
        if not explicit:  # mã tự sinh bị trùng thì thêm hậu tố -2, -3... (mã người dùng đặt thì báo lỗi)
            base, n = bid, 2
            while self._repo.book(bid).exists():
                bid, n = f"{base}-{n}", n + 1
        store = self._repo.book(bid)
        if store.exists():
            raise ConflictError(f"Mã '{bid}' đã được dùng cho một sách khác.")
        try:
            profile = default_profile(bid, title, engine or None)
        except ProfileError as exc:
            raise InvalidError(str(exc)) from exc
        head = await upload.read(4)
        if head != _PDF_MAGIC:
            raise InvalidError("File tải lên không phải là PDF.")
        # ghi tạm ra đĩa để đếm trang rồi đẩy lên MinIO; file tạm luôn bị xoá
        tmp_dir = Path(tempfile.mkdtemp(prefix="toc_upload_"))
        tmp = tmp_dir / "source.pdf"
        try:
            size = 4
            with tmp.open("wb") as f:
                f.write(head)
                while chunk := await upload.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise InvalidError(
                            f"File PDF quá lớn (tối đa {MAX_PDF_BYTES >> 20} MB)."
                        )
                    await asyncio.to_thread(f.write, chunk)
            pages = await asyncio.to_thread(self._count_pages, tmp)
            await asyncio.to_thread(
                self._create_in_storage,
                store,
                title,
                tmp,
                profile,
                {
                    "pdf_name": upload.filename or "",
                    "pdf_bytes": size,
                    "pdf_pages": pages,
                },
            )
        except BaseException:
            await asyncio.to_thread(store.delete)
            raise
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return self.get_book(bid)

    @staticmethod
    def _count_pages(path: Path) -> int | None:
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(path)).pages)
        except Exception:
            return None

    @staticmethod
    def _create_in_storage(
        store: BookRecord,
        title: str,
        pdf: Path,
        profile: Profile,
        extra: dict[str, Any],
    ) -> None:
        store.files.put_file("source.pdf", pdf)
        store.create(title, extra, profile=profile.model_dump(mode="json"))

    def delete_book(self, book_id: str) -> None:
        self.ensure_idle(self._repo.open(book_id), "xóa")
        self._delete(book_id)

    def page_image(self, book_id: str, page: int) -> bytes:
        """PNG của một trang PDF để đối chiếu mục lục/định vị bằng mắt. Vẽ lần đầu rồi lưu vào MinIO (`page_img/`)."""
        store = self._repo.open(book_id)
        total = self.pdf_pages(store)
        if (
            not store.files.exists("source.pdf")
            or total is None
            or not 1 <= page <= total
        ):
            raise NotFoundError(f"page {page}")
        name = PAGE_IMAGE_KEY.format(page=page)
        cached = store.files.get_bytes(name)
        if cached is not None:
            return cached
        tmp_dir = Path(tempfile.mkdtemp(prefix="toc_page_"))
        try:
            out = tmp_dir / "page"
            try:
                subprocess.run(
                    [
                        "pdftoppm",
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        "-r",
                        str(PAGE_IMAGE_DPI),
                        "-png",
                        "-singlefile",
                        str(self.local_pdf(store)),
                        str(out),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise InvalidError(
                    f"Không hiển thị được hình ảnh trang {page}: {exc}"
                ) from exc
            data = out.with_suffix(".png").read_bytes()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        store.files.put_bytes(name, data)
        return data

    def get_toc(self, book_id: str) -> dict[str, Any]:
        store = self._repo.open(book_id)
        doc = store.files.read_json("toc.json")
        if doc is None:
            raise NotFoundError("toc.json")
        return camelize(doc)

    def update_toc(self, book_id: str, body: TocUpdate) -> None:
        """Lưu chỉnh sửa mục lục của người duyệt vào override (bảng `book_overrides`, stage `toc`). Caller áp lại bước `toc` sau đó."""
        store = self._repo.open(book_id)
        if not (
            body.items
            or body.revert
            or body.deleted
            or body.restored
            or body.added
            or body.removed_added
            or body.offset is not None
            or body.clear_offset
        ):
            raise InvalidError("Không có thay đổi nào để lưu.")
        auto = store.files.read_json("toc.auto.json")
        if auto is None:
            raise ConflictError("Hãy làm bước Mục lục trước.")
        ids = {e["id"] for e in auto["entries"]}
        ov = store.overrides("toc")
        added = list(ov.get("_added") or [])
        ids |= {a["id"] for a in added}
        for it in body.items:
            if it.id not in ids:
                raise NotFoundError(it.id)
            cur = dict(ov.get(it.id) or {})
            if it.title is not None:
                if not it.title.strip():
                    raise InvalidError("Tên mục không được để trống.")
                cur["title"] = it.title.strip()
            if it.level is not None:
                cur["level"] = it.level
            if it.printed_page is not None:
                cur["printed_page"] = it.printed_page
            if it.clear_page:
                cur["printed_page"] = None
            ov[it.id] = cur
            for a in added:  # mục thêm tay sửa thẳng vào bản ghi của nó
                if a["id"] == it.id:
                    a.update(
                        {
                            k: v
                            for k, v in cur.items()
                            if k in {"title", "level", "printed_page"}
                        }
                    )
        for i in body.revert:
            ov.pop(i, None)
        for d in body.deleted:
            if d not in ids:
                raise NotFoundError(d)
        ov["_deleted"] = sorted(
            (set(ov.get("_deleted") or []) | set(body.deleted))
            - set(body.restored)
        )
        for a in body.added:
            if a.after_id is not None and a.after_id not in ids:
                raise NotFoundError(a.after_id)
            added.append(
                {
                    "id": "x"
                    + sha(a.title, str(len(added)), json.dumps(sorted(ids)))[
                        :6
                    ],
                    "title": a.title.strip(),
                    "level": a.level,
                    "printed_page": a.printed_page,
                    "after": a.after_id,
                }
            )
        ov["_added"] = [
            a for a in added if a["id"] not in set(body.removed_added)
        ]
        if body.offset is not None:
            ov["_offset"] = body.offset
        if body.clear_offset:
            ov.pop("_offset", None)
        store.write_overrides("toc", ov)

    def list_chunks(
        self,
        book_id: str,
        q: str,
        node: str,
        only_review: bool,
        page: int,
        page_size: int,
    ) -> TocListOutput:
        store = self._repo.open(book_id)
        rows = store.files.read_jsonl("chunks.jsonl")
        review = {
            r["id"]: r["reason"]
            for r in store.files.read_json("review/chunks.json", []) or []
        }
        entries = (store.files.read_json("toc.json") or {}).get("entries", [])
        by_id = {e["id"]: e for e in entries}
        prefix: list[str] | None = None
        if node:
            if node not in by_id:
                raise NotFoundError(node)
            prefix = by_id[node]["path"]
        ql = q.strip().lower()
        picked = [
            c
            for c in rows
            if (prefix is None or c["toc_path"][: len(prefix)] == prefix)
            and (
                not ql
                or ql in c["text"].lower()
                or any(ql in h.lower() for h in c["toc_path"])
            )
            and (not only_review or c["chunk_id"] in review)
        ]
        by_path: dict[tuple[str, ...], int] = {}
        for (
            c
        ) in rows:  # số chunk dưới mỗi mục (kể cả mục con) cho cây điều hướng
            for k in range(1, len(c["toc_path"]) + 1):
                key = tuple(c["toc_path"][:k])
                by_path[key] = by_path.get(key, 0) + 1
        per_node = {
            e["id"]: by_path.get(tuple(e["path"]), 0)
            for e in entries
            if by_path.get(tuple(e["path"]))
        }
        items = [
            {**c, "review_reason": review.get(c["chunk_id"])}
            for c in _paginate(picked, page, page_size)
        ]
        return TocListOutput(
            items=camelize(items),
            total=len(picked),
            page=page,
            page_size=page_size,
            counts=camelize(
                {
                    "all": len(rows),
                    "review": len(review),
                    "tokens": sum(c["tokens"] for c in rows),
                    "per_node": per_node,
                }
            ),
        )

    def _delete(self, book_id: str) -> None:
        """Xoá sách: mọi đối tượng trong MinIO + các đoạn đã lưu trong Qdrant."""
        self.delete_chunks(book_id)
        self._repo.book(book_id).delete()
        shutil.rmtree(temp_root() / book_id, ignore_errors=True)

    # ---- cài đặt, nhật ký, trang nguồn, xuất chunk ----
    def get_settings(self, book_id: str) -> TocSettings:
        p = self.read_profile(self._repo.open(book_id))
        return TocSettings(
            title=p.title or book_id,
            engine=p.extraction.engine,
            docling_force_ocr=p.extraction.docling_force_ocr,
            docling_tables=p.extraction.docling_tables,
            noise_pages=p.extraction.noise_pages,
            llm_enabled=p.llm.enabled,
            llm_model=p.llm.model,
            max_tokens=p.chunking.max_tokens,
            min_tokens=p.chunking.min_tokens,
            boundary_level=p.chunking.boundary_level,
            breadcrumb=p.chunking.breadcrumb,
        )

    def update_settings(self, book_id: str, body: TocSettings) -> TocSettings:
        store = self._repo.open(book_id)
        self.ensure_idle(store, "đổi cài đặt")
        p = self.read_profile(store)
        p.title = body.title.strip()
        p.extraction.engine = body.engine
        p.extraction.docling_force_ocr = body.docling_force_ocr
        p.extraction.docling_tables = body.docling_tables
        p.extraction.noise_pages = [
            x.strip() for x in body.noise_pages if x.strip()
        ]
        p.llm.enabled, p.llm.model = body.llm_enabled, body.llm_model.strip()
        p.chunking.max_tokens, p.chunking.min_tokens = (
            body.max_tokens,
            body.min_tokens,
        )
        p.chunking.boundary_level, p.chunking.breadcrumb = (
            body.boundary_level,
            body.breadcrumb,
        )
        self.save_profile(store, p)
        store.update_meta(title=p.title)
        return self.get_settings(book_id)

    def stage_log(self, book_id: str, stage_id: str, lines: int) -> str:
        store = self._repo.open(book_id)
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        return store.tail_log(stage_id, lines)

    def get_page(self, book_id: str, page: int) -> dict[str, Any]:
        store = self._repo.open(book_id)
        for r in store.files.iter_jsonl("pages.jsonl"):
            if r["page"] == page:
                return camelize(r)
        raise NotFoundError(f"page {page}")

    def export_chunks(self, book_id: str) -> bytes:
        store = self._repo.open(book_id)
        data = store.files.get_bytes("chunks.jsonl")
        if data is None:
            raise NotFoundError("chunks.jsonl")
        return data

    # ---- chunk trong Qdrant ----
    @staticmethod
    def point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def ensure_collection(self, dim: int) -> None:
        self._qdrant.ensure_collection_sync(self.collection, dim, keyword_index_fields=("book_id",))

    def delete_chunks(self, book_id: str) -> None:
        """Xoá mọi point của sách (no-op khi collection chưa có)."""
        self._qdrant.delete_by_filter_sync(self.collection, eq_filter("book_id", book_id))

    def count_chunks(self, book_id: str) -> int:
        return self._qdrant.count_sync(self.collection, eq_filter("book_id", book_id))

    def upsert_chunks(self, book_id: str, chunks: list[dict[str, Any]], vectors: list[list[float]], extra: dict[str, Any]) -> None:
        points = [
            PointStruct(id=self.point_id(c["chunk_id"]), vector=v,
                        payload={**{k: c.get(k) for k in _PAYLOAD_KEYS}, "book_id": book_id, **extra})
            for c, v in zip(chunks, vectors, strict=True)
        ]
        self._qdrant.upsert_points_sync(self.collection, points)
