"""DTO Input cho pipeline tài liệu."""
from typing import Any, Literal

from pydantic import BaseModel, Field



class RunStageInput(BaseModel):
    options: dict[str, Any] = {}
    force: bool = False  # bỏ qua kiểm tra bước phụ thuộc đã duyệt


class DocumentSettings(BaseModel):
    """Phần cấu hình của tài liệu sửa được trên giao diện (ghi vào `documents.profile`)."""

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


class TocItem(BaseModel):
    """Sửa một mục của mục lục. Trường để trống = không đổi; `clear_page` = đặt số trang về rỗng."""

    id: str
    title: str | None = None
    level: int | None = Field(default=None, ge=0, le=3)
    page_printed: int | None = Field(default=None, ge=0)  # override lưu dưới khoá `printed_page` (khớp `toc.json`)
    clear_page: bool = False


class TocNew(BaseModel):
    title: str = Field(min_length=1)
    level: int = Field(default=2, ge=0, le=3)
    page_printed: int | None = Field(default=None, ge=0)
    after_id: str | None = None  # chèn sau mục này; trống = cuối danh sách


class TocUpdate(BaseModel):
    items: list[TocItem] = []
    revert: list[str] = []  # bỏ mọi sửa tay của các mục này
    deleted: list[str] = []
    restored: list[str] = []  # hoàn tác xoá
    added: list[TocNew] = []
    removed_added: list[str] = []  # id mục thêm tay cần xoá
    offset: int | None = None  # trang PDF = trang in + offset; đặt tay thì thắng độ lệch tự suy
    clear_offset: bool = False  # quay về độ lệch tự suy
