"""Nghiệp vụ tài liệu"""
import asyncio
import contextlib
import json
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic import ValidationError
from qdrant_client.models import PointStruct

from app.dto.base.document import Document, NewDocument, DocumentStage
from app.dto.base.shared import File
from app.dto.common import FileDto
from app.dto.request.document import DocumentSettings, TocUpdate
from app.dto.response.document import (
    ChunkOutput,
    SourcePageOutput,
    TocOutput,
    DocumentOutput,
    DocumentSummary,
    ChunkListOutput,
    StageOutput,
)
from app.exception.errors import ConflictError, InvalidError, NotFoundError
from app.infra.bm25_sparse import SPARSE_NAME, encode_document
from app.infra.qdrant_client import QdrantVectorClient, eq_filter
from app.models.document_profile import Profile
from app.models.document_stage import STAGE_BY_ID, STAGES
from app.repositories.document_repository import DocumentRepository, now_iso
from pipeline.document_ingest.profile import ProfileError, default_profile
from pipeline.document_ingest.textutil import sha

_PAYLOAD_KEYS = ("chunk_id", "seq", "document_id", "text", "context_text", "part", "section", "topic", "subtopic", "toc_path", "toc_node_ids",
                 "figure_ids", "level", "pages_hint", "boundary", "suspect", "page_start", "page_end", "page_printed_start", "page_printed_end",
                 "tokens", "chars")

_PDF_MAGIC = b"%PDF"
MAX_PDF_BYTES = 500 * 1024 * 1024
PAGE_IMAGE_DPI = 80
PAGE_IMAGE_KEY = "page_img/p{page}.png"


def _paginate(
    rows: list[dict[str, Any]], page: int, page_size: int
) -> list[dict[str, Any]]:
    start = (max(page, 1) - 1) * page_size
    return rows[start : start + page_size]


def temp_root() -> Path:
    """Thư mục tạm cho `local_pdf()` (bản sao PDF để pdftotext/Docling/pdftoppm đọc, dùng xuyên suốt 1 lần chạy bước)."""
    p = Path(tempfile.gettempdir()) / "document_ingest_tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


class DocumentService:
    def __init__(self, repository: DocumentRepository, qdrant: QdrantVectorClient, collection: str) -> None:
        """`repository` = repository tài liệu"""
        self._repo, self.files = repository, repository.files
        self._qdrant, self.collection = qdrant, collection
        self.files.ensure_bucket()

    # ---- tiện ích trên repository ----
    @staticmethod
    def read_profile(repo: DocumentRepository, document_id: str) -> Profile:
        """Đọc cài đặt của tài liệu (`documents.profile`); thiếu hoặc sai thì báo lỗi hiển thị cho người dùng."""
        try:
            profile = repo.get_profile(document_id)
        except ValidationError as exc:
            raise InvalidError(f"Cài đặt của tài liệu bị lỗi: {exc}") from exc
        if profile is None:
            raise InvalidError("Cài đặt của tài liệu bị lỗi: tài liệu chưa có cài đặt")
        return profile

    @staticmethod
    def save_profile(repo: DocumentRepository, document_id: str, profile: Profile) -> None:
        repo.set_profile(document_id, profile)

    @staticmethod
    def blocking_deps(repo: DocumentRepository, document_id: str, stage_id: str, stages: dict[str, Any] | None = None) -> list[str]:
        """Các bước phụ thuộc CHƯA approved (rỗng = được phép chạy). Truyền `stages` (từ `repo.status()`) để khỏi đọc lại."""
        st = stages if stages is not None else repo.status(document_id)["stages"]
        return [d for d in STAGE_BY_ID[stage_id]["deps"] if st[d].get("state") != "approved"]

    @staticmethod
    def local_pdf(repo: DocumentRepository, document_id: str) -> Path:
        """Bản sao tạm của `source.pdf` trên đĩa, dùng lại khi cùng kích thước"""
        try:
            return repo.files_for(document_id).local_copy("source.pdf", temp_root() / document_id / "source.pdf")
        except FileNotFoundError as exc:
            raise FileNotFoundError("Không tìm thấy file PDF của tài liệu.") from exc

    @staticmethod
    @contextlib.contextmanager
    def temp_pdf_copy(repo: DocumentRepository, document_id: str) -> Generator[Path]:
        """Bản sao `source.pdf` dùng cho một lần gọi rồi xoá ngay"""
        with tempfile.TemporaryDirectory(prefix="toc_pdf_") as tmp:
            try:
                yield repo.files_for(document_id).local_copy("source.pdf", Path(tmp) / "source.pdf")
            except FileNotFoundError as exc:
                raise FileNotFoundError("Không tìm thấy file PDF của tài liệu.") from exc

    # ---- tài liệu ----
    def ensure_idle(self, document_id: str, action: str) -> None:
        running = [sid for sid, s in self._repo.status(document_id)["stages"].items() if s.get("state") == "running"]
        if running:
            raise ConflictError(f"Tài liệu đang được xử lý — hãy chờ xong hoặc dừng trước khi {action}.")

    def fail_orphaned_runs(self) -> int:
        """Bước ghi `running` nhưng không còn tiến trình nào chạy nó -> failed"""
        n = 0
        for did in self._repo.list_ids():
            for sid, st in self._repo.status(did)["stages"].items():
                if st.get("state") == "running":
                    self._repo.update_stage(
                        did,
                        sid,
                        state="failed",
                        finished_at=now_iso(),
                        error="Tiến trình xử lý đã dừng bất thường (xem nhật ký).",
                    )
                    n += 1
        return n

    def _document(self, document_id: str, detail: dict[str, Any]) -> Document:
        """`Document` nghiệp vụ của tài liệu — dựng từ `detail` (`DocumentRepository.get_detail`, gồm cả 2 dòng `files`)."""
        source = detail.get("source_file")
        ingested = detail.get("ingested_file")
        return Document(
            id=document_id,
            title=detail.get("title", document_id),
            type=detail.get("type", "book"),
            created_at=detail.get("created_at"),
            source_file=File(**source) if source else None,
            ingested_file=File(**ingested) if ingested else None,
            pdf_pages=self.pdf_pages(document_id) if source else None,
        )

    def _process_stages(self, document_id: str, detail: dict[str, Any]) -> list[DocumentStage]:
        """Trạng thái từng bước xử lý của tài liệu, dạng `DocumentStage` nghiệp vụ."""
        status = detail["stages"]
        out = []
        for s in STAGES:
            st = status[s["id"]]
            prog = st.get("progress")
            out.append(
                DocumentStage(
                    id=st.get("id") or f"{document_id}/{s['id']}",  # bước chưa có dòng DB (tài liệu cũ) chưa có id thật
                    stage_id=s["id"],
                    title=s["title"],
                    deps=s["deps"],
                    uses_llm=s["llm"],
                    state=st.get("state", "not_started"),
                    started_at=st.get("started_at"),
                    finished_at=st.get("finished_at"),
                    approved_at=st.get("approved_at"),
                    progress=prog if isinstance(prog, dict) else None,
                    summary=st.get("summary") or None,
                    error=st.get("error"),
                    options=st.get("options") or {},
                    blocked_by=self.blocking_deps(self._repo, document_id, s["id"], status),
                )
            )
        return out

    @staticmethod
    def _stage_output(stage: DocumentStage) -> StageOutput:
        """Map `DocumentStage` nghiệp vụ -> DTO wire cho API admin."""
        return StageOutput(
            stage_id=stage.stage_id,
            title=stage.title,
            deps=stage.deps,
            uses_llm=stage.uses_llm,
            state=stage.state,
            started_at=stage.started_at,
            finished_at=stage.finished_at,
            approved_at=stage.approved_at,
            progress=stage.progress,
            summary=stage.summary or None,
            error=stage.error,
            options=stage.options,
            blocked_by=stage.blocked_by,
        )

    def _stage_outputs(self, document_id: str, detail: dict[str, Any]) -> list[StageOutput]:
        return [self._stage_output(s) for s in self._process_stages(document_id, detail)]

    def list_documents(self) -> list[DocumentSummary]:
        out = []
        for did in self._repo.list_ids():
            detail = self._repo.get_detail(did)
            out.append(
                DocumentSummary(
                    id=did,
                    title=detail.get("title", did),
                    created_at=detail.get("created_at"),
                    states={k: v.get("state", "not_started") for k, v in detail["stages"].items()},
                )
            )
        return out

    def pdf_pages(self, document_id: str) -> int | None:
        cached = self._repo.meta(document_id).get("pdf_pages")
        if cached:
            return int(cached)
        try:
            with self.temp_pdf_copy(self._repo, document_id) as pdf:
                n = self._count_pages(pdf)
        except FileNotFoundError:
            return None
        if n is None:
            return None
        self._repo.update_meta(document_id, pdf_pages=n)
        return n

    def get_document(self, document_id: str) -> DocumentOutput:
        detail = self._repo.get_detail(document_id)
        if not detail:
            raise NotFoundError(document_id)
        document = self._document(document_id, detail)
        stages = self._stage_outputs(document_id, detail)
        return DocumentOutput(
            id=document.id,
            title=document.title,
            created_at=document.created_at,
            source_file=FileDto.model_validate(document.source_file.model_dump()) if document.source_file else None,
            pdf_pages=document.pdf_pages,
            stages=stages,
            running_stage=next(
                (s.stage_id for s in stages if s.state == "running"), None
            ),
        )

    async def create_document(
        self,
        upload: UploadFile,
        title: str,
        engine: str | None,
    ) -> DocumentOutput:
        try:
            draft = NewDocument.model_validate({"title": title, "engine": engine or "pdftotext"})
        except ValidationError as exc:
            raise InvalidError(exc.errors()[0]["msg"].removeprefix("Value error, ")) from exc
        head = await upload.read(4)
        if head != _PDF_MAGIC:
            raise InvalidError("File tải lên không phải là PDF.")
        tmp_dir = Path(tempfile.mkdtemp(prefix="toc_upload_"))
        try:
            tmp = tmp_dir / "source.pdf"
            await self._save_upload(upload, head, tmp)  # chỉ kiểm tra giới hạn; kích thước ghi vào `files` khi tạo
            pages = await asyncio.to_thread(self._count_pages, tmp)
            did = await asyncio.to_thread(
                self._repo.create,
                draft.title,
                {"pdf_pages": pages},
                default_profile("", draft.engine),
                {"source.pdf": tmp},
                None,
                upload.filename or "",
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return self.get_document(did)

    @staticmethod
    async def _save_upload(upload: UploadFile, head: bytes, dest: Path) -> int:
        """Ghi upload ra `dest` (đã đọc sẵn `head`), trả về số byte; quá giới hạn thì báo lỗi."""
        size = len(head)
        with dest.open("wb") as f:
            f.write(head)
            while chunk := await upload.read(1 << 20):
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise InvalidError(f"File PDF quá lớn (tối đa {MAX_PDF_BYTES >> 20} MB).")
                await asyncio.to_thread(f.write, chunk)
        return size

    @staticmethod
    def _count_pages(path: Path) -> int | None:
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(path)).pages)
        except Exception:
            return None

    def delete_document(self, document_id: str) -> None:
        self.ensure_idle(document_id, "xóa")
        self._delete(document_id)

    def page_image(self, document_id: str, page: int) -> bytes:
        """PNG của một trang PDF để đối chiếu mục lục/định vị bằng mắt. Vẽ lần đầu rồi lưu vào MinIO (`page_img/`)."""
        files = self._repo.files_for(document_id)
        total = self.pdf_pages(document_id)
        if (
            not files.exists("source.pdf")
            or total is None
            or not 1 <= page <= total
        ):
            raise NotFoundError(f"page {page}")
        name = PAGE_IMAGE_KEY.format(page=page)
        cached = files.get_bytes(name)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="toc_page_") as tmp_dir:
            out = Path(tmp_dir) / "page"
            try:
                with self.temp_pdf_copy(self._repo, document_id) as pdf:
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
                            str(pdf),
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
        files.put_bytes(name, data)
        return data

    def get_toc(self, document_id: str) -> TocOutput:
        doc = self._repo.files_for(document_id).read_json("toc.json")
        if doc is None:
            raise NotFoundError("toc.json")
        # `toc.json` giữ khoá lưu trữ cũ; đổi sang tên wire ở đây thay vì sửa dữ liệu đã có
        entries = [
            {**{k: v for k, v in e.items() if k not in ("printed_page", "pdf_page")},
             "page_printed": e.get("printed_page"), "page": e.get("pdf_page")}
            for e in doc.get("entries", [])
        ]
        return TocOutput.model_validate({**doc, "entries": entries})

    def update_toc(self, document_id: str, body: TocUpdate) -> None:
        """Lưu chỉnh sửa mục lục của người duyệt vào override (bảng `document_overrides`, stage `toc`). Caller áp lại bước `toc` sau đó."""
        files = self._repo.files_for(document_id)
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
        auto = files.read_json("toc.auto.json")
        if auto is None:
            raise ConflictError("Hãy làm bước Mục lục trước.")
        ids = {e["id"] for e in auto["entries"]}
        ov = self._repo.overrides.get(document_id, "toc")
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
            if it.page_printed is not None:
                cur["printed_page"] = it.page_printed
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
                    "printed_page": a.page_printed,
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
        self._repo.overrides.write(document_id, "toc", ov)

    def list_figures(self, document_id: str) -> list[dict[str, Any]]:
        return self._repo.files_for(document_id).read_json("figures.json", []) or []

    def figure_image(self, document_id: str, figure_id: str) -> bytes:
        files = self._repo.files_for(document_id)
        fig = next((f for f in files.read_json("figures.json", []) or [] if f["figure_id"] == figure_id), None)
        data = files.get_bytes(f"figures/{fig['image_file']['file_name']}") if fig else None
        if data is None:
            raise NotFoundError(figure_id)
        return data

    def list_chunks(
        self,
        document_id: str,
        q: str,
        node: str,
        only_review: bool,
        page: int,
        page_size: int,
    ) -> ChunkListOutput:
        files = self._repo.files_for(document_id)
        rows = files.read_jsonl("chunks.jsonl")
        review = {
            r["id"]: r["reason"]
            for r in files.read_json("review/chunks.json", []) or []
        }
        entries = (files.read_json("toc.json") or {}).get("entries", [])
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
            ChunkOutput.model_validate({**c, "review_reason": review.get(c["chunk_id"])})
            for c in _paginate(picked, page, page_size)
        ]
        return ChunkListOutput(
            items=items,
            total=len(picked),
            page=page,
            page_size=page_size,
            counts={
                "all": len(rows),
                "review": len(review),
                "tokens": sum(c["tokens"] for c in rows),
                "per_node": per_node,
            },
        )

    def _delete(self, document_id: str) -> None:
        """Xoá tài liệu: mọi đối tượng trong MinIO + các đoạn đã lưu trong Qdrant."""
        self.delete_chunks(document_id)
        self._repo.delete(document_id)
        shutil.rmtree(temp_root() / document_id, ignore_errors=True)

    # ---- cài đặt, nhật ký, trang nguồn, xuất chunk ----
    def get_settings(self, document_id: str) -> DocumentSettings:
        p = self.read_profile(self._repo, document_id)
        return DocumentSettings(
            title=self._repo.meta(document_id).get("title", document_id),
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

    def update_settings(self, document_id: str, body: DocumentSettings) -> DocumentSettings:
        self.ensure_idle(document_id, "đổi cài đặt")
        p = self.read_profile(self._repo, document_id)
        title = body.title.strip()
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
        self.save_profile(self._repo, document_id, p)
        self._repo.update_meta(document_id, title=title)
        return self.get_settings(document_id)

    def stage_log(self, document_id: str, stage_id: str, lines: int) -> str:
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        return self._repo.tail_log(document_id, stage_id, lines)

    def get_page(self, document_id: str, page: int) -> SourcePageOutput:
        for r in self._repo.files_for(document_id).iter_jsonl("pages.jsonl"):
            if r["page"] == page:
                return SourcePageOutput.model_validate(r)
        raise NotFoundError(f"page {page}")

    def export_chunks(self, document_id: str) -> bytes:
        data = self._repo.files_for(document_id).get_bytes("chunks.jsonl")
        if data is None:
            raise NotFoundError("chunks.jsonl")
        return data

    # ---- chunk trong Qdrant ----
    @staticmethod
    def point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def ensure_collection(self, dim: int) -> None:
        self._qdrant.ensure_collection_sync(self.collection, dim, keyword_index_fields=("document_id",), sparse_names=(SPARSE_NAME,))

    def delete_chunks(self, document_id: str) -> None:
        """Xoá mọi point của tài liệu (no-op khi collection chưa có)."""
        self._qdrant.delete_by_filter_sync(self.collection, eq_filter("document_id", document_id))

    def count_chunks(self, document_id: str) -> int:
        return self._qdrant.count_sync(self.collection, eq_filter("document_id", document_id))

    def upsert_chunks(self, document_id: str, chunks: list[dict[str, Any]], vectors: list[list[float]], extra: dict[str, Any]) -> None:
        points = [
            # vector không tên = dense (semantic); "bm25" = sparse để Qdrant chấm điểm từ khoá, cùng văn bản với embedding
            PointStruct(id=self.point_id(c["chunk_id"]), vector={"": v, SPARSE_NAME: encode_document(str(c.get("context_text") or c.get("text") or ""))},
                        payload={**{k: c.get(k) for k in _PAYLOAD_KEYS}, "document_id": document_id, **extra})
            for c, v in zip(chunks, vectors, strict=True)
        ]
        self._qdrant.upsert_points_sync(self.collection, points)
