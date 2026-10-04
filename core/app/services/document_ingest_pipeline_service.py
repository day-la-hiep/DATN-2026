"""Điều khiển pipeline `document_ingest`: kiểm tra điều kiện, chạy một bước, dừng, cổng duyệt (approve) và áp lại override.

Vòng đời: not_started -> running -> pending_review -> (approve) approved. Bước chỉ chạy khi mọi bước phụ thuộc đã
`approved`. Chạy lại một bước làm các bước hạ nguồn thành `stale`. `run_stage` chạy đồng bộ trong thread hiện tại; `start_stage` (API)
chạy ở thread nền riêng và trả về ngay, cờ dừng giữ trong `DocumentService` để `reconcile` biết bước nào thật sự còn chạy. Dữ liệu tài liệu
(CRUD, cài đặt, mục lục, chunk) do `DocumentService` lo. Client do `app/api/deps.py` tạo, truyền cho từng bước qua `StageContext`."""

import importlib
import threading
import traceback
from types import ModuleType
from typing import Any

from app.dto.request.document import TocUpdate
from app.dto.response.document import DocumentOutput
from app.exception.errors import (
    ConflictError,
    InvalidError,
    NotFoundError,
    PipelineError,
)
from app.infra.docling_client import DoclingClient
from app.infra.embedding_client import EmbeddingClient
from app.infra.llm_client import LLMClient
from app.models.document_stage import STAGE_BY_ID
from app.repositories.document_repository import DocumentRepository, now_iso
from app.services.document_service import DocumentService
from pipeline.document_ingest.stages import (
    StageCancelled,
    StageContext,
    StageError,
)


def _module(stage_id: str) -> ModuleType:
    if stage_id not in STAGE_BY_ID:
        raise NotFoundError(stage_id)
    return importlib.import_module(
        f"pipeline.document_ingest.stages.{stage_id}"
    )


class DocumentIngestPipelineService:
    """Điều khiển pipeline tài liệu: kiểm tra điều kiện, chạy bước (đồng bộ hoặc ở thread nền cho API), dừng, duyệt, áp lại override.
    Instance do `app/api/deps.py` tạo (một cho cả process)."""

    def __init__(
        self,
        documentService: DocumentService,
        repository: DocumentRepository,
        *,
        docling: DoclingClient | None = None,
        embedding: EmbeddingClient | None = None,
    ) -> None:
        self.documentService, self._repo = documentService, repository
        self._docling, self._embedding = docling, embedding

    def make_ctx(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> StageContext:
        profile = DocumentService.read_profile(self._repo, document_id)
        use_llm = STAGE_BY_ID[stage_id]["llm"] and profile.llm.enabled
        if use_llm and llm is None:
            llm = LLMClient(
                profile.llm.model,
                cache=self.documentService.files.scoped("_cache/llm/"),
            )
        return StageContext(
            document_id=document_id,
            files=self._repo.files_for(document_id),
            profile=profile,
            stage_id=stage_id,
            meta=lambda: self._repo.meta(document_id),
            overrides=lambda stage: self._repo.overrides.get(document_id, stage),
            _append_log=lambda stage, message: self._repo.append_log(document_id, stage, message),
            _update_stage=lambda stage, **fields: self._repo.update_stage(document_id, stage, **fields),
            llm=llm if use_llm else None,
            options=options,
            docling=self._docling,
            embedding=self._embedding,
            vectors=self.documentService,
            pdf=lambda: DocumentService.local_pdf(self._repo, document_id),
            cancel=cancel or threading.Event(),
        )

    # ---- chạy bước: check_runnable -> begin -> execute ----
    def check_runnable(
        self, document_id: str, stage_id: str, *, force: bool = False
    ) -> None:
        """Ném lỗi nếu chưa chạy được: bước không tồn tại, tài liệu đang xử lý bước khác, bước trước chưa duyệt (`force` bỏ qua), cài đặt
        hỏng. Gọi trước khi đưa sang thread nền để lỗi trả về ngay ở API."""
        if stage_id not in STAGE_BY_ID:
            raise NotFoundError(stage_id)
        status = self._repo.status(document_id)["stages"]
        running = [
            sid for sid, s in status.items() if s.get("state") == "running"
        ]
        if running:
            raise ConflictError(
                f"Đang xử lý bước “{STAGE_BY_ID[running[0]]['title']}” — hãy chờ xong hoặc dừng trước."
            )
        block = (
            []
            if force
            else DocumentService.blocking_deps(self._repo, document_id, stage_id, status)
        )
        if block:
            raise PipelineError(
                "Cần xác nhận các bước trước: "
                + ", ".join(STAGE_BY_ID[b]["title"] for b in block)
                + "."
            )
        DocumentService.read_profile(self._repo, document_id)

    def begin(
        self, document_id: str, stage_id: str, options: dict[str, Any]
    ) -> None:
        """Ghi trạng thái `running` (xoá nhật ký cũ, đánh dấu stale các bước hạ nguồn)."""
        self._repo.reset_log(document_id, stage_id)
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(
            document_id,
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
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        *,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Chạy bước đã `begin`, ghi kết quả `pending_review` / `failed` / `cancelled` cùng nhật ký."""
        try:
            ctx = self.make_ctx(document_id, stage_id, options, llm, cancel)
            ctx.log(f"bắt đầu bước {stage_id} options={options}")
            summary = _module(stage_id).run(ctx)
        except StageCancelled:
            self._repo.append_log(document_id, stage_id, "đã huỷ")
            self._repo.update_stage(
                document_id, stage_id, state="cancelled", finished_at=now_iso()
            )
            raise
        except Exception as e:
            self._repo.append_log(
                document_id,
                stage_id,
                "LỖI: " + "".join(traceback.format_exception(e))[-1500:],
            )
            msg = (
                str(e)
                if isinstance(e, (StageError, InvalidError))
                else f"{type(e).__name__}: {e}"
            )
            self._repo.update_stage(
                document_id, stage_id, state="failed", finished_at=now_iso(), error=msg
            )
            raise
        self._repo.update_stage(
            document_id,
            stage_id,
            state="pending_review",
            finished_at=now_iso(),
            summary=summary,
            error=None,
            progress={"done": 1, "total": 1, "message": "xong"},
        )
        if stage_id == "ingest":  # kết quả bước ingest là `Document.ingested_file` -> ghi thành dòng `files`
            self._repo.set_ingested_file(document_id, "pages.jsonl", "application/x-ndjson")
        ctx.log(f"xong: {summary}")
        return summary

    def run_stage(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any] | None = None,
        *,
        force: bool = False,
        llm: LLMClient | None = None,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Kiểm tra + chạy trọn một bước trong thread hiện tại."""
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        options = options or {}
        self.check_runnable(document_id, stage_id, force=force)
        self.begin(document_id, stage_id, options)
        return self.execute(document_id, stage_id, options, llm=llm, cancel=cancel)

    # ---- API admin: chạy nền / dừng / duyệt / áp lại, trả về trạng thái tài liệu ----
    def start_stage(
        self,
        document_id: str,
        stage_id: str,
        options: dict[str, Any],
        force: bool,
    ) -> DocumentOutput:
        """Kiểm tra điều kiện rồi chạy bước ở thread nền và trả về ngay (trạng thái `running`)."""
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        self.documentService.reconcile(document_id)
        self.check_runnable(document_id, stage_id, force=force)
        cancel = self.documentService.track_run(document_id, stage_id)
        self.begin(document_id, stage_id, options)

        def work() -> None:
            try:
                self.execute(document_id, stage_id, options, cancel=cancel)
            except Exception:  # noqa: BLE001 — runner đã ghi `failed`/`cancelled` + nhật ký
                pass
            finally:
                self.documentService.untrack_run(document_id, stage_id)

        threading.Thread(
            target=work,
            name=f"document-pipeline-{document_id}-{stage_id}",
            daemon=True,
        ).start()
        return self.documentService.get_document(document_id)

    def cancel_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        cancel = self.documentService.run_cancel_event(document_id, stage_id)
        if cancel is None:
            raise ConflictError("Bước này hiện không chạy.")
        cancel.set()  # bước dừng ở điểm kiểm tra gần nhất (giữa các cụm trang / nhóm gọi AI)
        return self.documentService.get_document(document_id)

    def approve_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        self.approve(document_id, stage_id)
        return self.documentService.get_document(document_id)

    def reapply_stage(
        self, document_id: str, stage_id: str
    ) -> DocumentOutput:
        self.reapply(document_id, stage_id)
        return self.documentService.get_document(document_id)

    def update_toc(
        self, document_id: str, body: TocUpdate
    ) -> DocumentOutput:
        """Lưu chỉnh sửa mục lục rồi áp lại bước `toc` (bước quay về chờ duyệt, các bước sau thành stale)."""
        self.documentService.update_toc(document_id, body)
        return self.reapply_stage(document_id, "toc")

    # ---- duyệt / áp override ----
    def approve(self, document_id: str, stage_id: str) -> dict[str, Any]:
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        st = self._repo.status(document_id)["stages"].get(stage_id)
        if st is None:
            raise NotFoundError(stage_id)
        if st.get("state") != "pending_review":
            raise PipelineError(
                "Chỉ xác nhận được bước đang ở trạng thái chờ xác nhận."
            )
        return self._repo.update_stage(
            document_id, stage_id, state="approved", approved_at=now_iso()
        )

    def reapply(self, document_id: str, stage_id: str) -> dict[str, Any]:
        """Áp lại override của người duyệt (nhanh, không LLM). Dữ liệu bước đổi nên bước quay về chờ duyệt và các bước hạ nguồn thành stale."""
        if not self._repo.exists(document_id):
            raise NotFoundError(document_id)
        mod = _module(stage_id)
        if not hasattr(mod, "reapply"):
            raise PipelineError(f"bước {stage_id} không có override")
        st = self._repo.status(document_id)["stages"][stage_id]
        if st.get("state") in {"not_started", "running"}:
            raise PipelineError(
                f"bước {stage_id} chưa có kết quả để áp override (hiện: {st.get('state')})"
            )
        summary = mod.reapply(
            self.make_ctx(document_id, stage_id, st.get("options") or {})
        )
        self._repo.mark_stale(document_id, stage_id)
        self._repo.update_stage(
            document_id, stage_id, state="pending_review", summary=summary, approved_at=None
        )
        return summary
