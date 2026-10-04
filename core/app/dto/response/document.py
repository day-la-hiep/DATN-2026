"""DTO Output cho pipeline tài liệu — nguồn: entity nghiệp vụ
`app/dto/base/document.py` (`Document`, `ProcessStage`), dựng bởi
`app/services/document_service.py`.

Record mục lục/chunk/trang do pipeline ghi ra MinIO ở dạng snake_case (`toc.json`,
`chunks.jsonl`, `pages.jsonl`) — các model dưới đây khai field bằng tên Python gốc đó rồi dựa
vào `CamelModel.model_config.alias_generator` để tự xuất camelCase khi serialize, không cần
đổi key bằng tay ở service."""
from typing import Any

from app.dto.common import CamelModel


class StageProgress(CamelModel):
    done: int = 0
    total: int = 0
    message: str = ""


class StageOutput(CamelModel):
    id: str
    title: str
    deps: list[str]
    uses_llm: bool
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    progress: StageProgress | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None
    options: dict[str, Any] = {}
    blocked_by: list[str] = []  # bước phụ thuộc chưa approved -> chưa được chạy


class DocumentSummary(CamelModel):
    id: str
    title: str
    created_at: str | None = None
    states: dict[str, str]


class DocumentOutput(CamelModel):
    id: str
    title: str
    created_at: str | None = None
    has_pdf: bool
    pdf_pages: int | None = None
    stages: list[StageOutput]
    running_stage: str | None = None  # tối đa một bước chạy mỗi tài liệu


class TocEntryOutput(CamelModel):
    """Một mục mục lục — nguồn: `pipeline/document_ingest/mapping.py::build_toc`/`hierarchy.py` (`toc.json["entries"]`)."""

    id: str
    level: int
    kind: str
    title: str
    printed_page: int | None = None
    toc_page: int | None = None
    suspect: bool = False
    suspect_reason: str | None = None
    edited: bool = False
    added: bool = False
    parent_id: str | None = None
    path: list[str] = []
    pdf_page: int | None = None
    anchor_line: int | None = None
    anchored: bool = False
    out_of_range: bool = False


class TocOutput(CamelModel):
    """Mục lục đầy đủ của một tài liệu — nguồn: `toc.json` (`mapping.py::build_toc`)."""

    toc_pages: list[int]
    pages_source: str
    entries: list[TocEntryOutput]
    offset: int | None = None
    offset_info: dict[str, Any] = {}
    total_pages: int
    anchored: int
    warnings: list[str] = []


class ChunkOutput(CamelModel):
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


class SourcePageOutput(CamelModel):
    """Một trang nguồn — nguồn: `pipeline/document_ingest/stages/ingest.py::_row` (`pages.jsonl`)."""

    page: int
    page_printed: int
    header: str
    text: str
    noise: bool
    noise_reason: str | None = None
    noise_score: float


class ChunkListOutput(CamelModel):
    items: list[ChunkOutput]
    total: int
    page: int
    page_size: int
    counts: dict[str, Any] = {}
