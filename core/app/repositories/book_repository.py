"""Repository sách giáo khoa (pipeline `book_ingest`).

- Bản ghi (bảng Postgres, `app/models/book.py`): sách + cài đặt (`books`), trạng thái từng bước (`book_stages`), override của người
  duyệt (`book_overrides`). Đọc-sửa-ghi trong transaction (khoá dòng `FOR UPDATE`) vì Core và các thread xử lý cùng ghi.
- File (MinIO, `toc/<book_id>/`, qua `FileStoreService` generic ở `record.files`): PDF, `pages.jsonl`, mục lục, chunk, ảnh trang, nhật ký.

Code ĐỒNG BỘ (session `PostgresClient.sync_session_factory`) vì pipeline chạy trong thread nền; caller async bọc `asyncio.to_thread`."""
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.exception.errors import NotFoundError
from app.models.book import Book, BookOverride, BookStage
from app.models.book_stage import STAGE_IDS, downstream
from app.services.file_store_service import FileStoreService

BOOK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")
ROOT_PREFIX = "toc/"
LOG_FLUSH_SECONDS = 1.5
_STAGE_TIMES = ("started_at", "finished_at", "approved_at")
_STAGE_FIELDS = {"state", "options", "progress", "summary", "error", *_STAGE_TIMES}

SessionFactory = Callable[[], Session]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat(timespec="seconds")


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _deep_merge(dst: dict[str, Any], patch: dict[str, Any]) -> None:
    """Gộp đệ quy `patch` vào `dst`; giá trị None xoá khoá (hoàn tác một override)."""
    for k, v in patch.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


def _stage_dict(row: BookStage) -> dict[str, Any]:
    out: dict[str, Any] = {"state": row.state}
    for k in ("options", "progress", "summary", "error"):
        if getattr(row, k) is not None:
            out[k] = getattr(row, k)
    for k in _STAGE_TIMES:
        out[k] = _iso(getattr(row, k))
    return out


class BookRecord:
    """Bản ghi của MỘT sách (tạo qua `BookRepository.book`)."""

    def __init__(self, book_id: str, books_root: FileStoreService, session_factory: SessionFactory):
        """`books_root` = kho file của bucket sách; tự thu hẹp về `toc/<book_id>/`."""
        if not BOOK_ID_RE.match(book_id):
            raise ValueError(f"book_id không hợp lệ: {book_id!r} (a-z, 0-9, _ -; 2-64 ký tự)")
        self.book_id = book_id
        self.files = books_root.scoped(f"{ROOT_PREFIX}{book_id}/")
        self._sessions = session_factory
        self._log_buf: dict[str, list[str]] = {}
        self._log_at: dict[str, float] = {}
        self._log_lock = threading.Lock()

    @contextmanager
    def _tx(self) -> Iterator[Session]:
        with self._sessions() as s, s.begin():
            yield s

    def _book_row(self, s: Session, *, lock: bool = False) -> Book:
        stmt = select(Book).where(Book.id == self.book_id)
        row = s.scalars(stmt.with_for_update() if lock else stmt).first()
        if row is None:
            raise NotFoundError(self.book_id)
        return row

    # ---- sách ----
    def exists(self) -> bool:
        with self._sessions() as s:
            return s.get(Book, self.book_id) is not None

    def meta(self) -> dict[str, Any]:
        with self._sessions() as s:
            b = s.get(Book, self.book_id)
            if b is None:
                return {}
            return {"id": b.id, "title": b.title, "created_at": _iso(b.created_at), "pdf_name": b.pdf_name,
                    "pdf_bytes": b.pdf_bytes, "pdf_pages": b.pdf_pages}

    def update_meta(self, **fields: Any) -> None:
        """Sửa cột của sách (`title`, `pdf_pages`...)."""
        with self._tx() as s:
            b = self._book_row(s, lock=True)
            for k, v in fields.items():
                setattr(b, k, v)

    def profile_data(self) -> dict[str, Any] | None:
        with self._sessions() as s:
            b = s.get(Book, self.book_id)
            return None if b is None else b.profile

    def set_profile_data(self, data: dict[str, Any]) -> None:
        self.update_meta(profile=data)

    def create(self, title: str, extra: dict[str, Any] | None = None, profile: dict[str, Any] | None = None) -> None:
        """Tạo sách + một dòng `not_started` cho mỗi bước. `extra`: pdf_name / pdf_bytes / pdf_pages."""
        with self._tx() as s:
            if s.get(Book, self.book_id) is not None:
                raise FileExistsError(f"sách {self.book_id!r} đã tồn tại")
            s.add(Book(id=self.book_id, title=title or self.book_id, profile=profile, **(extra or {})))
            s.flush()
            s.add_all(BookStage(book_id=self.book_id, stage_id=sid, state="not_started") for sid in STAGE_IDS)

    def delete(self) -> None:
        """Xoá bản ghi (bước + override xoá theo) và mọi file của sách. Bản sao PDF tạm và điểm Qdrant do `BookService.delete_book` xoá."""
        with self._tx() as s:
            s.execute(delete(BookOverride).where(BookOverride.book_id == self.book_id))
            s.execute(delete(BookStage).where(BookStage.book_id == self.book_id))
            s.execute(delete(Book).where(Book.id == self.book_id))
        self.files.delete_prefix()

    # ---- trạng thái các bước ----
    def status(self) -> dict[str, Any]:
        with self._sessions() as s:
            rows = {r.stage_id: _stage_dict(r) for r in s.scalars(select(BookStage).where(BookStage.book_id == self.book_id))}
        return {"stages": {sid: rows.get(sid, {"state": "not_started"}) for sid in STAGE_IDS}}

    def update_stage(self, stage_id: str, **fields: Any) -> dict[str, Any]:
        unknown = set(fields) - _STAGE_FIELDS
        if unknown:
            raise ValueError(f"trường trạng thái không hợp lệ: {sorted(unknown)}")
        with self._tx() as s:
            row = s.scalars(select(BookStage).where(BookStage.book_id == self.book_id, BookStage.stage_id == stage_id)
                            .with_for_update()).first()
            if row is None:
                self._book_row(s)
                row = BookStage(book_id=self.book_id, stage_id=stage_id, state="not_started")
                s.add(row)
            for k, v in fields.items():
                setattr(row, k, _dt(v) if k in _STAGE_TIMES else v)
            s.flush()
            return _stage_dict(row)

    def mark_stale(self, stage_id: str) -> list[str]:
        """Đánh dấu stale các bước hạ nguồn đã có kết quả (gọi khi `stage_id` chạy lại)."""
        marked: list[str] = []
        with self._tx() as s:
            rows = s.scalars(select(BookStage).where(BookStage.book_id == self.book_id,
                                                     BookStage.stage_id.in_(downstream(stage_id))).with_for_update())
            for row in rows:
                if row.state in {"pending_review", "approved", "failed", "cancelled"}:
                    row.state = "stale"
                    marked.append(row.stage_id)
        return marked

    # ---- override của người duyệt ----
    def overrides(self, stage_id: str) -> dict[str, Any]:
        with self._sessions() as s:
            row = s.get(BookOverride, (self.book_id, stage_id))
            return dict(row.data) if row is not None else {}

    def _set_overrides(self, stage_id: str, change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        with self._tx() as s:
            self._book_row(s, lock=True)  # khoá dòng sách: hai lần sửa cùng lúc không ghi đè nhau
            row = s.get(BookOverride, (self.book_id, stage_id))
            data = change(dict(row.data) if row is not None else {})
            if row is None:
                s.add(BookOverride(book_id=self.book_id, stage_id=stage_id, data=data))
            else:
                row.data = data
            return data

    def update_overrides(self, stage_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Gộp `patch` vào override của bước. Giá trị None xoá khoá."""

        def merge(cur: dict[str, Any]) -> dict[str, Any]:
            _deep_merge(cur, patch)
            return cur

        return self._set_overrides(stage_id, merge)

    def write_overrides(self, stage_id: str, data: dict[str, Any]) -> None:
        self._set_overrides(stage_id, lambda _: data)

    # ---- nhật ký: object không nối thêm được nên gom trong bộ nhớ và ghi cả file theo chu kỳ ----
    def _log_name(self, stage_id: str) -> str:
        return f"logs/{stage_id}.log"

    def reset_log(self, stage_id: str) -> None:
        with self._log_lock:
            self._log_buf[stage_id] = []
            self._log_at[stage_id] = 0.0
        self.files.delete(self._log_name(stage_id))

    def append_log(self, stage_id: str, message: str) -> None:
        with self._log_lock:
            buf = self._log_buf.setdefault(stage_id, [])
            buf.append(f"{now_iso()} {message}")
            due = time.monotonic() - self._log_at.get(stage_id, 0.0) >= LOG_FLUSH_SECONDS
        if due:
            self.flush_logs(stage_id)

    def flush_logs(self, stage_id: str | None = None) -> None:
        with self._log_lock:
            ids = [stage_id] if stage_id else list(self._log_buf)
            snap = {s: "\n".join(self._log_buf.get(s, [])) for s in ids}
            for s in ids:
                self._log_at[s] = time.monotonic()
        for s, text in snap.items():
            if text:
                self.files.put_text(self._log_name(s), text + "\n")

    def tail_log(self, stage_id: str, lines: int = 200) -> str:
        text = self.files.get_text(self._log_name(stage_id))
        return "" if not text else "\n".join(text.splitlines()[-lines:])


class BookRepository:
    """Repository sách. Instance do `app/api/deps.py` tạo (kho file bucket sách + session Postgres đồng bộ), inject vào service."""

    def __init__(self, files: FileStoreService, session_factory: SessionFactory) -> None:
        self.files, self._sessions = files, session_factory

    def book(self, book_id: str) -> BookRecord:
        """Bản ghi của một sách (ném ValueError nếu mã không hợp lệ)."""
        return BookRecord(book_id, self.files, self._sessions)

    def open(self, book_id: str) -> BookRecord:
        """Bản ghi của một sách ĐÃ tồn tại; mã sai hoặc chưa có sách -> NotFoundError."""
        try:
            record = self.book(book_id)
        except ValueError as exc:
            raise NotFoundError(book_id) from exc
        if not record.exists():
            raise NotFoundError(book_id)
        return record

    def list_ids(self) -> list[str]:
        with self._sessions() as s:
            return list(s.scalars(select(Book.id).order_by(Book.id)))
