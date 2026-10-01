"""Điều khiển pipeline `book_ingest`: kiểm tra điều kiện, chạy một bước, dừng, cổng duyệt (approve) và áp lại override.

Vòng đời: not_started -> running -> pending_review -> (approve) approved. Bước chỉ chạy khi mọi bước phụ thuộc đã
`approved`. Chạy lại một bước làm các bước hạ nguồn thành `stale`. `run_stage` chạy đồng bộ trong thread hiện tại; `start_stage` (API)
chạy ở thread nền riêng và trả về ngay, cờ dừng giữ trong `BookService` để `reconcile` biết bước nào thật sự còn chạy. Dữ liệu sách
(CRUD, cài đặt, mục lục, chunk) do `BookService` lo. Client do `app/api/deps.py` tạo, truyền cho từng bước qua `StageContext`."""

import importlib
import threading
import traceback
from types import ModuleType
from typing import Any

from app.dto.toc_pipeline import TocBookOutput, TocUpdate
from app.exception.errors import (
    ConflictError,
    InvalidError,
    NotFoundError,
    PipelineError,
)
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from app.models.book_stage import STAGE_BY_ID
from app.repositories.book_repository import BookRecord, BookRepository, now_iso
from app.services.book_service import BookService
from pipeline.book_ingest.stages import StageCancelled, StageContext, StageError


def _module(stage_id: str) -> ModuleType:
    if stage_id not in STAGE_BY_ID:
        raise NotFoundError(stage_id)
    return importlib.import_module(f"pipeline.book_ingest.stages.{stage_id}")


class BookIngestPipelineService:
    """Điều khiển pipeline sách: kiểm tra điều kiện, chạy bước (đồng bộ hoặc ở thread nền cho API), dừng, duyệt, áp lại override.
    Instance do `app/api/deps.py` tạo (một cho cả process)."""

    def __init__(
        self,
        bookService: BookService,
        repository: BookRepository,
        *,
        docling: DoclingClient | None = None,
        embedding: EmbeddingClient | None = None,
    ) -> None:
        self.bookService, self._repo = bookService, repository
        self._docling, self._embedding = docling, embedding

    def make_ctx(
        self,
        store: BookRecord,
        stage_id: str,
        options: dict[str, Any],
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> StageContext:
        profile = BookService.read_profile(store)
        use_llm = STAGE_BY_ID[stage_id]["llm"] and profile.llm.enabled
        if use_llm and llm is None:
            llm = LLMClient(
                profile.llm.model,
                cache=self.bookService.files.scoped("_cache/llm/"),
            )
        return StageContext(
            store=store,
            profile=profile,
            stage_id=stage_id,
            llm=llm if use_llm else None,
            options=options,
            docling=self._docling,
            embedding=self._embedding,
            vectors=self.bookService,
            pdf=lambda: BookService.local_pdf(store),
            cancel=cancel or threading.Event(),
        )

    # ---- chạy bước: check_runnable -> begin -> execute ----
    def check_runnable(
        self, store: BookRecord, stage_id: str, *, force: bool = False
    ) -> None:
        """Ném lỗi nếu chưa chạy được: bước không tồn tại, sách đang xử lý bước khác, bước trước chưa duyệt (`force` bỏ qua), cài đặt
        hỏng. Gọi trước khi đưa sang thread nền để lỗi trả về ngay ở API."""
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        status = store.status()["stages"]
        running = [
            sid for sid, s in status.items() if s.get("state") == "running"
        ]
        if running:
            raise ConflictError(
                f"Đang xử lý bước “{STAGE_BY_ID[running[0]]['title']}” — hãy chờ xong hoặc dừng trước."
            )
        block = (
            [] if force else BookService.blocking_deps(store, stage_id, status)
        )
        if block:
            raise PipelineError(
                "Cần xác nhận các bước trước: "
                + ", ".join(STAGE_BY_ID[b]["title"] for b in block)
                + "."
            )
        BookService.read_profile(store)

    def begin(
        self, store: BookRecord, stage_id: str, options: dict[str, Any]
    ) -> None:
        """Ghi trạng thái `running` (xoá nhật ký cũ, đánh dấu stale các bước hạ nguồn)."""
        store.reset_log(stage_id)
        store.mark_stale(stage_id)
        store.update_stage(
            stage_id,
            state="running",
            started_at=now_iso(),
            finished_at=None,
            error=None,
            options=options,
            progress={"done": 0, "total": 0, "message": "bắt đầu"},
            summary=None,
            approved_at=None,
        )

    def execute(
        self,
        store: BookRecord,
        stage_id: str,
        options: dict[str, Any],
        *,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Chạy bước đã `begin`, ghi kết quả `pending_review` / `failed` / `cancelled` cùng nhật ký."""
        try:
            ctx = self.make_ctx(store, stage_id, options, llm, cancel)
            ctx.log(f"bắt đầu bước {stage_id} options={options}")
            summary = _module(stage_id).run(ctx)
        except StageCancelled:
            store.append_log(stage_id, "đã huỷ")
            store.update_stage(
                stage_id, state="cancelled", finished_at=now_iso()
            )
            store.flush_logs()
            raise
        except Exception as e:
            store.append_log(
                stage_id,
                "LỖI: " + "".join(traceback.format_exception(e))[-1500:],
            )
            msg = (
                str(e)
                if isinstance(e, (StageError, InvalidError))
                else f"{type(e).__name__}: {e}"
            )
            store.update_stage(
                stage_id, state="failed", finished_at=now_iso(), error=msg
            )
            store.flush_logs()
            raise
        store.update_stage(
            stage_id,
            state="pending_review",
            finished_at=now_iso(),
            summary=summary,
            error=None,
            progress={"done": 1, "total": 1, "message": "xong"},
        )
        ctx.log(f"xong: {summary}")
        store.flush_logs()
        return summary

    def run_stage(
        self,
        book_id: str,
        stage_id: str,
        options: dict[str, Any] | None = None,
        *,
        force: bool = False,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Kiểm tra + chạy trọn một bước trong thread hiện tại."""
        store = self._repo.book(book_id)
        if not store.exists():
            raise NotFoundError(book_id)
        options = options or {}
        self.check_runnable(store, stage_id, force=force)
        self.begin(store, stage_id, options)
        return self.execute(store, stage_id, options, llm=llm, cancel=cancel)

    # ---- API admin: chạy nền / dừng / duyệt / áp lại, trả về trạng thái sách ----
    def start_stage(
        self, book_id: str, stage_id: str, options: dict[str, Any], force: bool
    ) -> TocBookOutput:
        """Kiểm tra điều kiện rồi chạy bước ở thread nền và trả về ngay (trạng thái `running`)."""
        store = self._repo.open(book_id)
        self.bookService.reconcile(store)
        self.check_runnable(store, stage_id, force=force)
        cancel = self.bookService.track_run(book_id, stage_id)
        self.begin(store, stage_id, options)

        def work() -> None:
            try:
                self.execute(store, stage_id, options, cancel=cancel)
            except Exception:  # noqa: BLE001 — runner đã ghi `failed`/`cancelled` + nhật ký
                pass
            finally:
                self.bookService.untrack_run(book_id, stage_id)

        threading.Thread(
            target=work, name=f"book-pipeline-{book_id}-{stage_id}", daemon=True
        ).start()
        return self.bookService.get_book(book_id)

    def cancel_stage(self, book_id: str, stage_id: str) -> TocBookOutput:
        self._repo.open(book_id)
        cancel = self.bookService.run_cancel_event(book_id, stage_id)
        if cancel is None:
            raise ConflictError("Bước này hiện không chạy.")
        cancel.set()  # bước dừng ở điểm kiểm tra gần nhất (giữa các cụm trang / nhóm gọi AI)
        return self.bookService.get_book(book_id)

    def approve_stage(self, book_id: str, stage_id: str) -> TocBookOutput:
        self.approve(self._repo.open(book_id).book_id, stage_id)
        return self.bookService.get_book(book_id)

    def reapply_stage(self, book_id: str, stage_id: str) -> TocBookOutput:
        self.reapply(self._repo.open(book_id).book_id, stage_id)
        return self.bookService.get_book(book_id)

    def update_toc(self, book_id: str, body: TocUpdate) -> TocBookOutput:
        """Lưu chỉnh sửa mục lục rồi áp lại bước `toc` (bước quay về chờ duyệt, các bước sau thành stale)."""
        self.bookService.update_toc(book_id, body)
        return self.reapply_stage(book_id, "toc")

    # ---- duyệt / áp override ----
    def approve(self, book_id: str, stage_id: str) -> dict[str, Any]:
        store = self._repo.book(book_id)
        st = store.status()["stages"].get(stage_id)
        if st is None:
            raise NotFoundError(stage_id)
        if st.get("state") != "pending_review":
            raise PipelineError(
                "Chỉ xác nhận được bước đang ở trạng thái chờ xác nhận."
            )
        return store.update_stage(
            stage_id, state="approved", approved_at=now_iso()
        )

    def reapply(self, book_id: str, stage_id: str) -> dict[str, Any]:
        """Áp lại override của người duyệt (nhanh, không LLM). Dữ liệu bước đổi nên bước quay về chờ duyệt và các bước hạ nguồn thành stale."""
        store = self._repo.book(book_id)
        mod = _module(stage_id)
        if not hasattr(mod, "reapply"):
            raise PipelineError(f"bước {stage_id} không có override")
        st = store.status()["stages"][stage_id]
        if st.get("state") in {"not_started", "running"}:
            raise PipelineError(
                f"bước {stage_id} chưa có kết quả để áp override (hiện: {st.get('state')})"
            )
        summary = mod.reapply(
            self.make_ctx(store, stage_id, st.get("options") or {})
        )
        store.mark_stale(stage_id)
        store.update_stage(
            stage_id, state="pending_review", summary=summary, approved_at=None
        )
        return summary
