"""Cấu hình của một tài liệu"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractionConfig(_Model):
    # "docling" = OCR ảnh trang (PDF scan / lớp text hỏng); "pdftotext" = dùng lớp text có sẵn (nhanh).
    engine: Literal["pdftotext", "docling"] = "pdftotext"
    docling_force_ocr: bool = True
    docling_tables: bool = True  # giữ cấu trúc bảng: mục lục thường là bảng
    docling_chunk_pages: int = Field(default=20, ge=1, le=100)  # số trang mỗi lần gọi (có checkpoint, huỷ được)
    layout: bool = False  # pdftotext -layout
    strip_running_headers: bool = True
    noise_pages: list[str] = []  # "1-30", "937-968": bỏ qua hoàn toàn khi chunk
    page_offset: int = 0  # số trang in = trang PDF + offset, chỉ dùng khi không đọc được số trang in từ chữ


class LLMConfig(_Model):
    enabled: bool = True
    # id ngắn trong `settings.AGENT_MODEL_CHOICES` hoặc "provider:model". Rỗng = model mặc định của agent.
    model: str = ""


class ChunkingConfig(_Model):
    max_tokens: int = Field(default=400, ge=50, le=4000)  # ước lượng, không phải tokenizer thật
    min_tokens: int = Field(default=60, ge=0, le=1000)  # chunk nhỏ hơn số này vào hàng đợi xem lại
    # Chunk không bao giờ vượt ranh giới của mục có cấp <= số này (0 part, 1 section, 2 mục, 3 mục con).
    boundary_level: int = Field(default=3, ge=0, le=3)
    breadcrumb: bool = True  # thêm đường dẫn mục lục vào `context_text` (dùng khi embed)


class IndexingConfig(_Model):
    # Ngôn ngữ chính của sách, quyết định cách xử lý chữ cho tìm từ khoá (BM25): vi = tách từ ghép tiếng Việt, en = stem tiếng Anh
    # (bỏ bước tách từ chậm), mixed = cả hai.
    text_language: Literal["vi", "en", "mixed"] = "mixed"


class Profile(_Model):
    document_id: str
    language: str = "en"
    extraction: ExtractionConfig = ExtractionConfig()
    llm: LLMConfig = LLMConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    indexing: IndexingConfig = IndexingConfig()
