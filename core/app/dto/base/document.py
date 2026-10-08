"""Bounded context Tài liệu: sách / guideline số hoá qua pipeline ingest."""

from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from app.dto.base.identity import Doctor
from app.dto.base.shared import File


class DocumentChunk(BaseModel):
    """Một đoạn chunk theo khung mục lục của `Document` — CHỈ tồn tại khi `Document.type ==
    "book"` (các loại khác không qua pipeline chunk). Nguồn:
    `pipeline/document_ingest/stages/chunks.py::build_chunks` (`chunks.jsonl`)."""

    chunk_id: str
    seq: int
    document_id: str
    text: str
    context_text: str
    part: str = ""
    section: str = ""
    topic: str = ""
    subtopic: str = ""
    toc_path: list[str] = []
    toc_node_ids: list[str] = []
    figure_ids: list[
        str
    ] = []  # ảnh nằm trong khoảng trang của chunk (xem `DocumentFigure`)
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


class DocumentFigure(BaseModel):
    """Một ảnh (hình minh hoạ, sơ đồ, biểu đồ) được trích từ trang của `Document` type "book". Nguồn: bước Đọc nội dung
    (engine docling) -> `figures.json`. `caption` là chữ chú thích đi kèm trong sách để tìm kiếm, không phải mô tả do AI sinh."""

    figure_id: str
    document_id: str
    page: int
    seq: int
    bbox: list[float] | None = None  # [trái, trên, phải, dưới] trên trang PDF
    image_file: File
    caption: str = ""


class DocumentStageOverride(BaseModel):
    """Chỉnh sửa tay của người duyệt lên kết quả một bước (`DocumentStage.overrides`) — nguồn:
    `app/models/document.py::DocumentOverride`. Lưu riêng khỏi kết quả máy để chạy lại bước không mất công sửa."""

    data: dict[str, Any] = {}
    updated_at: str | None = None


class DocumentStage(BaseModel):
    """Trạng thái một bước xử lý của một `Document` (`Document.stages`) — nguồn: `app/models/document.py::DocumentStage`
    + hằng nghiệp vụ `app/models/document_stage.py::STAGES`."""

    id: str
    stage_id: str
    title: str
    deps: list[str] = []
    uses_llm: bool = False
    state: str = "not_started"
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    progress: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None
    options: dict[str, Any] = {}
    blocked_by: list[str] = []
    overrides: list[DocumentStageOverride] = []  # sửa tay của người duyệt cho bước này


class Document(BaseModel):
    """Một tài liệu được upload — field chung cho MỌI loại; field riêng của từng loại để
    optional=None khi không áp dụng (cùng quy ước với `MessageMetadata`, xem `docs/db-diagram.md`
    mục 2). Hiện chỉ loại `"book"` (pipeline `document_ingest`, nguồn: `app/models/document.py::Document`)
    được xử lý sâu (OCR, mục lục, chunk — xem `stages`/`DocumentChunk`); các loại khác là
    tệp người dùng đính kèm tin nhắn, chưa qua pipeline nào.

    File đi kèm là `File` (`app/dto/base/shared.py`): `source_file` là file gốc người dùng upload,
    `ingested_file` là file JSON sau bước ingest (`pages.jsonl`); chunk nằm trong `chunks`."""

    id: str
    title: str
    type: Literal["book", "image", "video", "other"]
    created_at: str | None = None
    source_file: File | None = None
    ingested_file: File | None = (
        None  # chỉ có khi type == "book" và đã qua bước ingest
    )
    pdf_pages: int | None = None  # chỉ có khi type == "book"
    uploaded_by: Doctor | None = (
        None  # chỉ bác sĩ được tải tài liệu lên; None với tài liệu tạo trước khi có đăng nhập
    )
    chunks: list[DocumentChunk] | None = None  # chỉ có khi type == "book"
    figures: list[DocumentFigure] | None = None  # chỉ có khi type == "book"
    stages: list[DocumentStage] = []  # các bước xử lý (ingest/toc/chunks/index), mỗi bước giữ override của nó

    @model_validator(mode="after")
    def validate_type(self):
        if self.type != "book":
            if self.pdf_pages is not None:
                raise ValueError(
                    'pdf_pages chỉ áp dụng cho Document type="book"'
                )
            if self.chunks is not None:
                raise ValueError('chunks chỉ áp dụng cho Document type="book"')
            if self.figures is not None:
                raise ValueError('figures chỉ áp dụng cho Document type="book"')
            if self.ingested_file is not None:
                raise ValueError(
                    'ingested_file chỉ áp dụng cho Document type="book"'
                )
        return self


class NewDocument(BaseModel):
    """Đầu vào tạo tài liệu mới — validate tại đây. Mã tài liệu do DB sinh khi tạo."""

    title: str
    engine: Literal["pdftotext", "docling"] = "pdftotext"

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Vui lòng nhập tên tài liệu.")
        return v
