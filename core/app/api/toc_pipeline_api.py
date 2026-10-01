"""Router admin luồng chunk theo mục lục — `/admin/toc-pipeline/*`.

Mọi endpoint nằm sau `require_app_token` (xem `main.py`). Bước nặng chạy nền bằng subprocess: endpoint `run` trả về
ngay, FE poll `GET /books/{id}` để thấy trạng thái/tiến độ."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response

from app.dto.common import ApiResponse
from app.dto.toc_pipeline import (
    TocBookOutput,
    TocBookSummary,
    TocListOutput,
    TocRunInput,
    TocSettings,
    TocUpdate,
)
from app.api.deps import get_book_service, get_book_ingest_pipeline_service
from app.services.book_ingest_pipeline_service import BookIngestPipelineService
from app.services.book_service import BookService

router = APIRouter(prefix="/admin/toc-pipeline", tags=["admin-toc-pipeline"])

Service = Annotated[
    BookIngestPipelineService, Depends(get_book_ingest_pipeline_service)
]
Books = Annotated[BookService, Depends(get_book_service)]


async def _call(fn: Any, *args: Any) -> Any:
    """Chạy hàm đồng bộ của service (đọc/ghi MinIO) ngoài event loop; lỗi domain do exception handler đổi sang HTTP."""
    return await asyncio.to_thread(fn, *args)


# ------------------------------------------------------------------ sách
@router.get(
    "/books",
    response_model=ApiResponse[list[TocBookSummary]],
    operation_id="listTocBooks",
)
async def list_books(books: Books) -> ApiResponse[list[TocBookSummary]]:
    return ApiResponse(data=await _call(books.list_books))


@router.post(
    "/books",
    response_model=ApiResponse[TocBookOutput],
    status_code=201,
    operation_id="createTocBook",
)
async def create_book(
    books: Books,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    book_id: Annotated[str | None, Form(alias="bookId")] = None,
    engine: Annotated[str | None, Form()] = None,
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(
        data=await books.create_book(file, title, book_id, engine or None)
    )


@router.get(
    "/books/{book_id}",
    response_model=ApiResponse[TocBookOutput],
    operation_id="getTocBook",
)
async def get_book(book_id: str, books: Books) -> ApiResponse[TocBookOutput]:
    return ApiResponse(data=await _call(books.get_book, book_id))


@router.delete(
    "/books/{book_id}", status_code=204, operation_id="deleteTocBook"
)
async def delete_book(book_id: str, books: Books) -> Response:
    await _call(books.delete_book, book_id)
    return Response(status_code=204)


@router.get(
    "/books/{book_id}/settings",
    response_model=ApiResponse[TocSettings],
    operation_id="getTocSettings",
)
async def get_settings(book_id: str, books: Books) -> ApiResponse[TocSettings]:
    return ApiResponse(data=await _call(books.get_settings, book_id))


@router.put(
    "/books/{book_id}/settings",
    response_model=ApiResponse[TocSettings],
    operation_id="updateTocSettings",
)
async def update_settings(
    book_id: str, body: TocSettings, books: Books
) -> ApiResponse[TocSettings]:
    return ApiResponse(data=await _call(books.update_settings, book_id, body))


# ------------------------------------------------------------------ chạy bước
@router.post(
    "/books/{book_id}/stages/{stage_id}/run",
    response_model=ApiResponse[TocBookOutput],
    status_code=202,
    operation_id="runTocStage",
)
async def run_stage(
    book_id: str, stage_id: str, body: TocRunInput, svc: Service
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(
        data=await _call(
            svc.start_stage, book_id, stage_id, body.options, body.force
        )
    )


@router.post(
    "/books/{book_id}/stages/{stage_id}/cancel",
    response_model=ApiResponse[TocBookOutput],
    operation_id="cancelTocStage",
)
async def cancel_stage(
    book_id: str, stage_id: str, svc: Service
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(data=await _call(svc.cancel_stage, book_id, stage_id))


@router.post(
    "/books/{book_id}/stages/{stage_id}/approve",
    response_model=ApiResponse[TocBookOutput],
    operation_id="approveTocStage",
)
async def approve_stage(
    book_id: str, stage_id: str, svc: Service
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(data=await _call(svc.approve_stage, book_id, stage_id))


@router.post(
    "/books/{book_id}/stages/{stage_id}/reapply",
    response_model=ApiResponse[TocBookOutput],
    operation_id="reapplyTocStage",
)
async def reapply_stage(
    book_id: str, stage_id: str, svc: Service
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(data=await _call(svc.reapply_stage, book_id, stage_id))


@router.get(
    "/books/{book_id}/stages/{stage_id}/log",
    response_model=ApiResponse[str],
    operation_id="getTocStageLog",
)
async def stage_log(
    book_id: str,
    stage_id: str,
    books: Books,
    lines: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> ApiResponse[str]:
    return ApiResponse(
        data=await _call(books.stage_log, book_id, stage_id, lines)
    )


# ------------------------------------------------------------------ trang nguồn
@router.get(
    "/books/{book_id}/pages/{page}",
    response_model=ApiResponse[dict[str, Any]],
    operation_id="getTocPage",
)
async def get_page(
    book_id: str, page: int, books: Books
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(data=await _call(books.get_page, book_id, page))


@router.get(
    "/books/{book_id}/pages/{page}/image", operation_id="getTocPageImage"
)
async def get_page_image(book_id: str, page: int, books: Books) -> Response:
    data = await _call(books.page_image, book_id, page)
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ------------------------------------------------------------------ mục lục / chunk
@router.get(
    "/books/{book_id}/toc",
    response_model=ApiResponse[dict[str, Any]],
    operation_id="getTocTree",
)
async def get_toc(book_id: str, books: Books) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(data=await _call(books.get_toc, book_id))


@router.patch(
    "/books/{book_id}/toc",
    response_model=ApiResponse[TocBookOutput],
    operation_id="updateTocTree",
)
async def update_toc(
    book_id: str, body: TocUpdate, svc: Service
) -> ApiResponse[TocBookOutput]:
    return ApiResponse(data=await _call(svc.update_toc, book_id, body))


@router.get(
    "/books/{book_id}/chunks",
    response_model=ApiResponse[TocListOutput],
    operation_id="listTocChunks",
)
async def list_chunks(
    book_id: str,
    books: Books,
    q: str = "",
    node: str = "",
    only_review: Annotated[bool, Query(alias="onlyReview")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> ApiResponse[TocListOutput]:
    return ApiResponse(
        data=await _call(
            books.list_chunks, book_id, q, node, only_review, page, page_size
        )
    )


@router.get("/books/{book_id}/chunks/export", operation_id="exportTocChunks")
async def export_chunks(book_id: str, books: Books) -> Response:
    data = await _call(books.export_chunks, book_id)
    return Response(
        data,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{book_id}-chunks.jsonl"'
        },
    )
