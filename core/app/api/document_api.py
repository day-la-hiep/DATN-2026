"""Router admin pipeline tài liệu — `/admin/documents/*`.

Mọi endpoint nằm sau `require_app_token` (xem `main.py`). Bước nặng chạy nền bằng subprocess: endpoint `run` trả về
ngay, FE poll `GET /documents/{id}` để thấy trạng thái/tiến độ."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import get_document_ingest_pipeline_service, get_document_service
from app.dto.common import ApiResponse
from app.dto.request.document import RunStageInput, DocumentSettings, TocUpdate
from app.dto.response.document import (
    SourcePageOutput,
    TocOutput,
    DocumentOutput,
    DocumentSummary,
    ChunkListOutput,
    FigureOutput,
)
from app.services.document_ingest_pipeline_service import DocumentIngestPipelineService
from app.services.document_service import DocumentService

router = APIRouter(prefix="/admin/documents", tags=["admin-documents"])

Service = Annotated[
    DocumentIngestPipelineService, Depends(get_document_ingest_pipeline_service)
]
Documents = Annotated[DocumentService, Depends(get_document_service)]


async def _call(fn: Any, *args: Any) -> Any:
    """Chạy hàm đồng bộ của service (đọc/ghi MinIO) ngoài event loop; lỗi domain do exception handler đổi sang HTTP."""
    return await asyncio.to_thread(fn, *args)


# ------------------------------------------------------------------ tài liệu
@router.get(
    "/documents",
    response_model=ApiResponse[list[DocumentSummary]],
    operation_id="listTocDocuments",
)
async def list_documents(documents: Documents) -> ApiResponse[list[DocumentSummary]]:
    return ApiResponse(data=await _call(documents.list_documents))


@router.post(
    "/documents",
    response_model=ApiResponse[DocumentOutput],
    status_code=201,
    operation_id="createTocDocument",
)
async def create_document(
    documents: Documents,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    engine: Annotated[str | None, Form()] = None,
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(
        data=await documents.create_document(file, title, engine or None)
    )


@router.get(
    "/documents/{document_id}",
    response_model=ApiResponse[DocumentOutput],
    operation_id="getTocDocument",
)
async def get_document(document_id: str, documents: Documents) -> ApiResponse[DocumentOutput]:
    return ApiResponse(data=await _call(documents.get_document, document_id))


@router.delete(
    "/documents/{document_id}", status_code=204, operation_id="deleteTocDocument"
)
async def delete_document(document_id: str, documents: Documents) -> Response:
    await _call(documents.delete_document, document_id)
    return Response(status_code=204)


@router.get(
    "/documents/{document_id}/settings",
    response_model=ApiResponse[DocumentSettings],
    operation_id="getDocumentSettings",
)
async def get_settings(document_id: str, documents: Documents) -> ApiResponse[DocumentSettings]:
    return ApiResponse(data=await _call(documents.get_settings, document_id))


@router.put(
    "/documents/{document_id}/settings",
    response_model=ApiResponse[DocumentSettings],
    operation_id="updateDocumentSettings",
)
async def update_settings(
    document_id: str, body: DocumentSettings, documents: Documents
) -> ApiResponse[DocumentSettings]:
    return ApiResponse(data=await _call(documents.update_settings, document_id, body))


# ------------------------------------------------------------------ chạy bước
@router.post(
    "/documents/{document_id}/stages/{stage_id}/run",
    response_model=ApiResponse[DocumentOutput],
    status_code=202,
    operation_id="runTocStage",
)
async def run_stage(
    document_id: str, stage_id: str, body: RunStageInput, svc: Service
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(
        data=await svc.start_stage(document_id, stage_id, body.options, body.force)
    )


@router.post(
    "/documents/{document_id}/stages/{stage_id}/cancel",
    response_model=ApiResponse[DocumentOutput],
    operation_id="cancelTocStage",
)
async def cancel_stage(
    document_id: str, stage_id: str, svc: Service
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(data=await svc.cancel_stage(document_id, stage_id))


@router.post(
    "/documents/{document_id}/stages/{stage_id}/approve",
    response_model=ApiResponse[DocumentOutput],
    operation_id="approveTocStage",
)
async def approve_stage(
    document_id: str, stage_id: str, svc: Service
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(data=await _call(svc.approve_stage, document_id, stage_id))


@router.post(
    "/documents/{document_id}/stages/{stage_id}/reapply",
    response_model=ApiResponse[DocumentOutput],
    operation_id="reapplyTocStage",
)
async def reapply_stage(
    document_id: str, stage_id: str, svc: Service
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(data=await _call(svc.reapply_stage, document_id, stage_id))


@router.get(
    "/documents/{document_id}/stages/{stage_id}/log",
    response_model=ApiResponse[str],
    operation_id="getTocStageLog",
)
async def stage_log(
    document_id: str,
    stage_id: str,
    documents: Documents,
    lines: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> ApiResponse[str]:
    return ApiResponse(
        data=await _call(documents.stage_log, document_id, stage_id, lines)
    )


# ------------------------------------------------------------------ trang nguồn
@router.get(
    "/documents/{document_id}/pages/{page}",
    response_model=ApiResponse[SourcePageOutput],
    operation_id="getTocPage",
)
async def get_page(
    document_id: str, page: int, documents: Documents
) -> ApiResponse[SourcePageOutput]:
    return ApiResponse(data=await _call(documents.get_page, document_id, page))


@router.get(
    "/documents/{document_id}/pages/{page}/image", operation_id="getTocPageImage"
)
async def get_page_image(document_id: str, page: int, documents: Documents) -> Response:
    data = await _call(documents.page_image, document_id, page)
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ------------------------------------------------------------------ mục lục / chunk
@router.get(
    "/documents/{document_id}/toc",
    response_model=ApiResponse[TocOutput],
    operation_id="getTocTree",
)
async def get_toc(document_id: str, documents: Documents) -> ApiResponse[TocOutput]:
    return ApiResponse(data=await _call(documents.get_toc, document_id))


@router.patch(
    "/documents/{document_id}/toc",
    response_model=ApiResponse[DocumentOutput],
    operation_id="updateTocTree",
)
async def update_toc(
    document_id: str, body: TocUpdate, svc: Service
) -> ApiResponse[DocumentOutput]:
    return ApiResponse(data=await _call(svc.update_toc, document_id, body))


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ApiResponse[ChunkListOutput],
    operation_id="listTocChunks",
)
async def list_chunks(
    document_id: str,
    documents: Documents,
    q: str = "",
    node: str = "",
    only_review: Annotated[bool, Query()] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResponse[ChunkListOutput]:
    return ApiResponse(
        data=await _call(
            documents.list_chunks, document_id, q, node, only_review, page, page_size
        )
    )


# ------------------------------------------------------------------ hình ảnh trong sách
@router.get(
    "/documents/{document_id}/figures",
    response_model=ApiResponse[list[FigureOutput]],
    operation_id="listTocFigures",
)
async def list_figures(
    document_id: str, documents: Documents
) -> ApiResponse[list[FigureOutput]]:
    rows = await _call(documents.list_figures, document_id)
    return ApiResponse(data=[FigureOutput.model_validate(r) for r in rows])


@router.get(
    "/documents/{document_id}/figures/{figure_id}/image",
    operation_id="getTocFigureImage",
)
async def get_figure_image(
    document_id: str, figure_id: str, documents: Documents
) -> Response:
    data = await _call(documents.figure_image, document_id, figure_id)
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/documents/{document_id}/chunks/export", operation_id="exportTocChunks")
async def export_chunks(document_id: str, documents: Documents) -> Response:
    data = await _call(documents.export_chunks, document_id)
    return Response(
        data,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{document_id}-chunks.jsonl"'
        },
    )
