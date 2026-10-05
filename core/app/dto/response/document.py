"""DTO Output cho pipeline tài liệu — nguồn: entity nghiệp vụ `app/dto/base/document.py` (`Document`, `DocumentStage`,
`DocumentChunk`, `DocumentFigure`), dựng bởi `app/services/document_service.py`. Wire dùng snake_case như tên field Python."""
from typing import Any

from pydantic import BaseModel

from app.dto.common import FileDto


class StageOutput(BaseModel):
    """Field khớp `DocumentStage` (bỏ `document_id`: đã có ở URL)."""

    stage_id: str
    title: str
    deps: list[str]
    uses_llm: bool
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    progress: dict[str, Any] | None = None  # {done, total, message}
    summary: dict[str, Any] | None = None
    error: str | None = None
    options: dict[str, Any] = {}
    blocked_by: list[str] = []  # bước phụ thuộc chưa approved -> chưa được chạy


class DocumentSummary(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    states: dict[str, str]


class DocumentOutput(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    source_file: FileDto | None = None  # None = chưa có PDF gốc
    pdf_pages: int | None = None
    stages: list[StageOutput]
    running_stage: str | None = None  # tối đa một bước chạy mỗi tài liệu; tính từ `stages`


class TocEntryOutput(BaseModel):
    """Một mục mục lục — nguồn: `pipeline/document_ingest/mapping.py::build_toc`/`hierarchy.py` (`toc.json["entries"]`).
    `page_printed`/`page` là tên wire (khớp `DocumentChunk.page_printed_*`, `DocumentFigure.page`); `toc.json` vẫn lưu
    `printed_page`/`pdf_page` — service đổi tên khi đọc (`DocumentService.get_toc`) để không phải sửa dữ liệu đã có."""

    id: str
    level: int
    kind: str
    title: str
    page_printed: int | None = None
    toc_page: int | None = None
    suspect: bool = False
    suspect_reason: str | None = None
    edited: bool = False
    added: bool = False
    parent_id: str | None = None
    path: list[str] = []
    page: int | None = None  # trang PDF
    anchor_line: int | None = None
    anchored: bool = False
    out_of_range: bool = False


class TocOutput(BaseModel):
    """Mục lục đầy đủ của một tài liệu — nguồn: `toc.json` (`mapping.py::build_toc`)."""

    toc_pages: list[int]
    pages_source: str
    entries: list[TocEntryOutput]
    offset: int | None = None
    offset_info: dict[str, Any] = {}
    total_pages: int
    anchored: int
    warnings: list[str] = []


class ChunkOutput(BaseModel):
    """Một chunk — nguồn: `pipeline/document_ingest/stages/chunks.py::build_chunks` (`chunks.jsonl`)."""

    chunk_id: str
    seq: int
    text: str
    context_text: str
    part: str = ""
    section: str = ""
    topic: str = ""
    subtopic: str = ""
    toc_path: list[str] = []
    toc_node_ids: list[str] = []
    figure_ids: list[str] = []
    level: int
    pages_hint: list[int]
    boundary: bool
    suspect: bool
    page_start: int
    page_end: int
    page_printed_start: int
    page_printed_end: int
    tokens: int
    chars: int
    review_reason: str | None = None


class SourcePageOutput(BaseModel):
    """Một trang nguồn — nguồn: `pipeline/document_ingest/stages/ingest.py::_row` (`pages.jsonl`)."""

    page: int
    page_printed: int
    header: str
    text: str
    noise: bool
    noise_reason: str | None = None
    noise_score: float


class FigureOutput(BaseModel):
    """Một ảnh trong sách — nguồn: `pipeline/document_ingest/stages/ingest.py::_figure_rows` (`figures.json`)."""

    figure_id: str
    document_id: str
    page: int
    seq: int
    bbox: list[float] | None = None
    caption: str = ""


class ChunkListOutput(BaseModel):
    items: list[ChunkOutput]
    total: int
    page: int
    page_size: int
    counts: dict[str, Any] = {}
