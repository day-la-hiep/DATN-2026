"""DTO API admin cho luồng chunk theo mục lục (`toc_pipeline/`).

Record dữ liệu (mục lục, chunk, trang) đi qua dạng `dict` đã đổi key sang camelCase
(`app/services/book_ingest_pipeline_service.py::camelize`) vì cấu trúc do pipeline định nghĩa."""
from typing import Any, Literal

from pydantic import Field

from app.dto.common import CamelModel


class TocProgress(CamelModel):
    done: int = 0
    total: int = 0
    message: str = ""


class TocStageOutput(CamelModel):
    id: str
    title: str
    deps: list[str]
    uses_llm: bool
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    progress: TocProgress | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None
    options: dict[str, Any] = {}
    blocked_by: list[str] = []  # bước phụ thuộc chưa approved -> chưa được chạy


class TocBookSummary(CamelModel):
    id: str
    title: str
    created_at: str | None = None
    states: dict[str, str]


class TocBookOutput(CamelModel):
    id: str
    title: str
    created_at: str | None = None
    has_pdf: bool
    pdf_pages: int | None = None
    stages: list[TocStageOutput]
    running_stage: str | None = None  # tối đa một bước chạy mỗi sách


class TocRunInput(CamelModel):
    options: dict[str, Any] = {}
    force: bool = False  # bỏ qua kiểm tra bước phụ thuộc đã duyệt


class TocSettings(CamelModel):
    """Phần cấu hình của sách sửa được trên giao diện (ghi vào `books.profile`)."""

    title: str = Field(min_length=1)
    engine: Literal["pdftotext", "docling"]
    docling_force_ocr: bool = True
    docling_tables: bool = True
    noise_pages: list[str] = []
    llm_enabled: bool = True
    llm_model: str = ""
    max_tokens: int = Field(ge=50, le=4000)
    min_tokens: int = Field(ge=0, le=1000)
    boundary_level: int = Field(ge=0, le=3)
    breadcrumb: bool = True


class TocItem(CamelModel):
    """Sửa một mục của mục lục. Trường để trống = không đổi; `clear_page` = đặt số trang về rỗng."""

    id: str
    title: str | None = None
    level: int | None = Field(default=None, ge=0, le=3)
    printed_page: int | None = Field(default=None, ge=0)
    clear_page: bool = False


class TocNew(CamelModel):
    title: str = Field(min_length=1)
    level: int = Field(default=2, ge=0, le=3)
    printed_page: int | None = Field(default=None, ge=0)
    after_id: str | None = None  # chèn sau mục này; trống = cuối danh sách


class TocUpdate(CamelModel):
    items: list[TocItem] = []
    revert: list[str] = []  # bỏ mọi sửa tay của các mục này
    deleted: list[str] = []
    restored: list[str] = []  # hoàn tác xoá
    added: list[TocNew] = []
    removed_added: list[str] = []  # id mục thêm tay cần xoá
    offset: int | None = None  # trang PDF = trang in + offset; đặt tay thì thắng độ lệch tự suy
    clear_offset: bool = False  # quay về độ lệch tự suy


class TocListOutput(CamelModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    counts: dict[str, Any] = {}
