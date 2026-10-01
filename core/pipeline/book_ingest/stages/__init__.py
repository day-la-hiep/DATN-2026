"""Các bước của pipeline. Mỗi module có `run(ctx) -> dict` (summary hiển thị cho người duyệt) và, nếu bước có
override của người duyệt, `reapply(ctx) -> dict` (áp lại override lên kết quả máy, KHÔNG gọi LLM)."""
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from app.models.book_profile import Profile

from .. import mapping

if TYPE_CHECKING:  # chỉ để khai báo kiểu; bước không gọi gì của app ngoài các client được truyền vào
    from app.repositories.book_repository import BookRecord


class ChunkIndex(Protocol):
    """Kho vector chunk của sách (cài đặt: `BookService`)."""

    collection: str

    def ensure_collection(self, dim: int) -> None: ...
    def delete_chunks(self, book_id: str) -> None: ...
    def count_chunks(self, book_id: str) -> int: ...
    def upsert_chunks(self, book_id: str, chunks: list[dict[str, Any]], vectors: list[list[float]], extra: dict[str, Any]) -> None: ...


class StageCancelled(Exception):
    pass


class StageError(RuntimeError):
    """Lỗi người dùng có thể sửa (thiếu file, tuỳ chọn sai...) — hiển thị nguyên văn ở UI."""


@dataclass
class StageContext:
    store: "BookRecord"
    profile: Profile
    stage_id: str
    llm: LLMClient | None = None
    # Các client do runner truyền vào (instance do `app/api/deps.py` quản lý); bước nào cần mới dùng.
    docling: DoclingClient | None = None
    embedding: EmbeddingClient | None = None
    vectors: ChunkIndex | None = None
    # trả về bản sao `source.pdf` trên đĩa cho công cụ cần file thật (pdftotext, Docling, pypdf)
    pdf: Callable[[], Path] | None = None
    options: dict[str, Any] = field(default_factory=dict)
    # Đặt khi người dùng bấm Dừng; các bước gọi `ctx.check_cancel()` (qua `progress`) ở vòng lặp lớn.
    cancel: threading.Event = field(default_factory=threading.Event)
    _last_write: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, message: str) -> None:
        self.store.append_log(self.stage_id, message)

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise StageCancelled()

    def progress(self, done: int, total: int, message: str = "") -> None:
        """Ghi tiến độ vào `book_stages` (giới hạn ~2 lần/giây để khỏi ghi DB dồn dập)."""
        self.check_cancel()
        with self._lock:
            now = time.monotonic()
            if done < total and now - self._last_write < 0.5:
                return
            self._last_write = now
        self.store.update_stage(self.stage_id, progress={"done": done, "total": total, "message": message})

    def require_llm(self) -> LLMClient:
        if self.llm is None:
            raise StageError("Bước này cần LLM nhưng profile đặt llm.enabled=false")
        return self.llm

    def require_docling(self) -> DoclingClient:
        if self.docling is None:
            raise StageError("Chưa cấu hình công cụ nhận dạng chữ (Docling).")
        return self.docling

    def require_embedding(self) -> EmbeddingClient:
        if self.embedding is None:
            raise StageError("Chưa cấu hình công cụ tạo vector (embedding).")
        return self.embedding

    def local_pdf(self) -> Path:
        if self.pdf is None:
            raise StageError("Không tìm thấy file PDF của sách.")
        return self.pdf()

    def require_vectors(self) -> ChunkIndex:
        if self.vectors is None:
            raise StageError("Chưa cấu hình kho vector (Qdrant).")
        return self.vectors


def refresh_toc(ctx: StageContext, total_pages: int) -> None:
    """Đọc kết quả AI + override + chữ các trang, tính lại cây/độ lệch/neo và ghi `toc.json` (dùng bởi bước Mục lục và Chia đoạn)."""
    store = ctx.store
    auto = store.files.read_json("toc.auto.json", None)
    if auto is None:
        raise StageError("Chưa đọc mục lục — hãy làm bước Mục lục trước.")
    store.files.write_json("toc.json", mapping.build_toc(auto, store.overrides("toc"), store.files.read_jsonl("pages.jsonl"), total_pages))
