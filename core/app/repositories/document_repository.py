"""Repository tài liệu (pipeline `document_ingest`) — stateless: mọi method nhận `document_id` thẳng (không có object
đã "mở" sẵn 1 tài liệu). Overrides của người duyệt tách riêng ở `DocumentOverrideRepository` (field `.overrides`).

- Bản ghi (bảng Postgres, `app/models/document.py`): tài liệu + cài đặt (`documents`), trạng thái từng bước
  (`document_stages`). Đọc-sửa-ghi trong transaction (khoá dòng `FOR UPDATE`) vì Core và các thread xử lý cùng ghi.
- File (MinIO, `document/<document_id>/`, qua `files_for(document_id)` — một `FileStoreService` đã scope, dựng lại mỗi
  lần gọi, không cache gì): PDF, `pages.jsonl`, mục lục, chunk, ảnh trang, nhật ký.

Code ĐỒNG BỘ (session `PostgresClient.sync_session_factory`) vì pipeline chạy trong thread nền; caller async bọc
`asyncio.to_thread`. Instance do `app/api/deps.py` tạo (một cho cả process), inject vào service."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.exception.errors import NotFoundError
from app.models.document import Document, DocumentOverride, DocumentStage
from app.models.document_profile import Profile
from app.models.document_stage import STAGE_IDS, downstream
from app.repositories.document_override_repository import DocumentOverrideRepository
from app.services.file_store_service import FileStoreService

ROOT_PREFIX = "document/"
_STAGE_TIMES = ("started_at", "finished_at", "approved_at")
_STAGE_FIELDS = {
    "state",
    "options",
    "progress",
    "summary",
    "error",
    *_STAGE_TIMES,
}

SessionFactory = Callable[[], Session]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat(timespec="seconds")


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _stage_dict(row: DocumentStage) -> dict[str, Any]:
    out: dict[str, Any] = {"state": row.state}
    for k in ("options", "progress", "summary", "error"):
        if getattr(row, k) is not None:
            out[k] = getattr(row, k)
    for k in _STAGE_TIMES:
        out[k] = _iso(getattr(row, k))
    return out


class DocumentRepository:
    """Repository tài liệu — mọi method nhận `document_id` thẳng; không giữ state riêng cho từng tài liệu (an toàn
    dùng chung 1 instance cho cả process, xem `app/api/deps.py`)."""

    def __init__(self, files: FileStoreService, session_factory: SessionFactory) -> None:
        self.files, self._sessions = files, session_factory
        self.overrides = DocumentOverrideRepository(session_factory)
        # (document_id, stage_id) -> dòng log của lần chạy đang diễn ra (chỉ 1 bước chạy mỗi tài liệu nên không cần khoá)
        self._log_buf: dict[tuple[str, str], list[str]] = {}

    @contextmanager
    def _tx(self) -> Iterator[Session]:
        with self._sessions() as s, s.begin():
            yield s

    def _row(self, s: Session, document_id: str, *, lock: bool = False) -> Document:
        stmt = select(Document).where(Document.id == document_id)
        row = s.scalars(stmt.with_for_update() if lock else stmt).first()
        if row is None:
            raise NotFoundError(document_id)
        return row

    def files_for(self, document_id: str) -> FileStoreService:
        """`FileStoreService` đã scope về `document/<document_id>/` — dựng lại mỗi lần gọi (không I/O, không cache)."""
        return self.files.scoped(f"{ROOT_PREFIX}{document_id}/")

    def list_ids(self) -> list[str]:
        with self._sessions() as s:
            return list(s.scalars(select(Document.id).order_by(Document.id)))

    # ---- tài liệu ----
    def exists(self, document_id: str) -> bool:
        with self._sessions() as s:
            return s.get(Document, document_id) is not None

    def meta(self, document_id: str) -> dict[str, Any]:
        with self._sessions() as s:
            b = s.get(Document, document_id)
            if b is None:
                return {}
            return {
                "id": b.id,
                "title": b.title,
                "created_at": _iso(b.created_at),
                "pdf_name": b.pdf_name,
                "pdf_bytes": b.pdf_bytes,
                "pdf_pages": b.pdf_pages,
            }

    def get_detail(self, document_id: str) -> dict[str, Any]:
        """`meta()` + trạng thái mọi bước trong 1 lần đọc (1 session, 2 query) — dùng cho "lấy chi tiết tài liệu"
        thay vì gọi `meta()` rồi `status()` riêng. Trả `{}` nếu tài liệu không tồn tại."""
        with self._sessions() as s:
            b = s.get(Document, document_id)
            if b is None:
                return {}
            stage_rows = {
                r.stage_id: _stage_dict(r)
                for r in s.scalars(select(DocumentStage).where(DocumentStage.document_id == document_id))
            }
        return {
            "id": b.id,
            "title": b.title,
            "created_at": _iso(b.created_at),
            "pdf_name": b.pdf_name,
            "pdf_bytes": b.pdf_bytes,
            "pdf_pages": b.pdf_pages,
            "stages": {sid: stage_rows.get(sid, {"state": "not_started"}) for sid in STAGE_IDS},
        }

    def update_meta(self, document_id: str, **fields: Any) -> None:
        """Sửa cột của tài liệu (`title`, `pdf_pages`...)."""
        with self._tx() as s:
            b = self._row(s, document_id, lock=True)
            for k, v in fields.items():
                setattr(b, k, v)

    def get_profile(self, document_id: str) -> Profile | None:
        """Cài đặt xử lý của tài liệu (JSON trong `documents.profile`, đọc qua Pydantic). `None` nếu tài liệu không tồn tại
        hoặc chưa có cài đặt; dữ liệu sai cấu trúc để Pydantic báo lỗi (`ValidationError`)."""
        with self._sessions() as s:
            b = s.get(Document, document_id)
            if b is None or b.profile is None:
                return None
            return Profile.model_validate({**b.profile, "document_id": document_id})

    def set_profile(self, document_id: str, profile: Profile) -> None:
        self.update_meta(document_id, profile=profile.model_dump(mode="json"))

    def create(
        self,
        title: str,
        extra: dict[str, Any],
        profile: Profile,
        files: dict[str, Path],
        document_id: str | None = None,
    ) -> str:
        """Tạo record tài liệu (+ một dòng `not_started` cho mỗi bước) và ghi `files` (tên trong thư mục tài liệu -> đường dẫn
        local) lên MinIO như MỘT thao tác: lỗi ở đâu thì rollback DB và xoá các file đã ghi. Trả về id do DB sinh
        (`document_id` chỉ dùng cho dữ liệu test cố định)."""
        uploaded: list[str] = []
        fs: FileStoreService | None = None
        try:
            with self._tx() as s:
                row = Document(title=title or "", **extra)
                if document_id is not None:
                    row.id = document_id
                s.add(row)
                s.flush()  # DB/ORM sinh id ở đây; các dòng sau và file dùng id này
                profile.document_id = row.id
                row.profile = profile.model_dump(mode="json")
                s.add_all(DocumentStage(document_id=row.id, stage_id=sid, state="not_started") for sid in STAGE_IDS)
                fs = self.files_for(row.id)
                for name, path in files.items():
                    fs.put_file(name, path)
                    uploaded.append(name)
        except BaseException:
            if fs is not None:
                for name in uploaded:
                    fs.delete(name)
            raise
        return row.id

    def delete(self, document_id: str) -> None:
        """Xoá bản ghi (bước + override xoá theo) và mọi file của tài liệu. Bản sao PDF tạm và điểm Qdrant do
        `DocumentService.delete_document` xoá."""
        with self._tx() as s:
            s.execute(delete(DocumentOverride).where(DocumentOverride.document_id == document_id))
            s.execute(delete(DocumentStage).where(DocumentStage.document_id == document_id))
            s.execute(delete(Document).where(Document.id == document_id))
        self.files_for(document_id).delete_prefix()

    # ---- trạng thái các bước ----
    def status(self, document_id: str) -> dict[str, Any]:
        with self._sessions() as s:
            rows = {
                r.stage_id: _stage_dict(r)
                for r in s.scalars(select(DocumentStage).where(DocumentStage.document_id == document_id))
            }
        return {"stages": {sid: rows.get(sid, {"state": "not_started"}) for sid in STAGE_IDS}}

    def update_stage(self, document_id: str, stage_id: str, **fields: Any) -> dict[str, Any]:
        unknown = set(fields) - _STAGE_FIELDS
        if unknown:
            raise ValueError(f"trường trạng thái không hợp lệ: {sorted(unknown)}")
        with self._tx() as s:
            row = s.scalars(
                select(DocumentStage)
                .where(DocumentStage.document_id == document_id, DocumentStage.stage_id == stage_id)
                .with_for_update()
            ).first()
            if row is None:
                self._row(s, document_id)
                row = DocumentStage(document_id=document_id, stage_id=stage_id, state="not_started")
                s.add(row)
            for k, v in fields.items():
                setattr(row, k, _dt(v) if k in _STAGE_TIMES else v)
            s.flush()
            return _stage_dict(row)

    def mark_stale(self, document_id: str, stage_id: str) -> list[str]:
        """Đánh dấu stale các bước hạ nguồn đã có kết quả (gọi khi `stage_id` chạy lại)."""
        marked: list[str] = []
        with self._tx() as s:
            rows = s.scalars(
                select(DocumentStage)
                .where(DocumentStage.document_id == document_id, DocumentStage.stage_id.in_(downstream(stage_id)))
                .with_for_update()
            )
            for row in rows:
                if row.state in {"pending_review", "approved", "failed", "cancelled"}:
                    row.state = "stale"
                    marked.append(row.stage_id)
        return marked

    # ---- nhật ký: object MinIO không nối thêm được, nên giữ các dòng trong RAM và ghi lại cả file mỗi lần
    # thêm dòng mới (một lần chạy bước chỉ log vài chục dòng — không cần gộp/trễ ghi) ----
    def _log_name(self, stage_id: str) -> str:
        return f"logs/{stage_id}.log"

    def reset_log(self, document_id: str, stage_id: str) -> None:
        self._log_buf.pop((document_id, stage_id), None)
        self.files_for(document_id).delete(self._log_name(stage_id))

    def append_log(self, document_id: str, stage_id: str, message: str) -> None:
        buf = self._log_buf.setdefault((document_id, stage_id), [])
        buf.append(f"{now_iso()} {message}")
        self.files_for(document_id).put_text(self._log_name(stage_id), "\n".join(buf) + "\n")

    def tail_log(self, document_id: str, stage_id: str, lines: int = 200) -> str:
        text = self.files_for(document_id).get_text(self._log_name(stage_id))
        return "" if not text else "\n".join(text.splitlines()[-lines:])
