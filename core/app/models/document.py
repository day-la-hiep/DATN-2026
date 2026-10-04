"""Tài liệu của pipeline `document_ingest` (hiện chỉ sách giáo khoa dạng PDF): bản ghi tài liệu,
trạng thái từng bước, override của người duyệt. Lớp entity nghiệp vụ tương ứng là
`app/dto/base/document.py::Document`/`ProcessStage`/`ProcessStageOverride` — các class ở đây CHỈ
là schema lưu trữ SQLAlchemy (xem `derma-core-conventions`).

File lớn (PDF, `pages.jsonl`, mục lục, chunk, ảnh trang, nhật ký) vẫn nằm trong MinIO dưới
`document/<document_id>/`; bảng chỉ giữ dữ liệu nhỏ hay bị sửa đồng thời (Core + thread xử lý) và cần
truy vấn. JSON dùng JSONB trên Postgres, JSON thường ở SQLite (test)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    title: Mapped[str] = mapped_column(String(255))
    # `Document.type` (base): "book" | "image" | "video" | "other" — hiện chỉ "book" đi qua pipeline
    type: Mapped[str] = mapped_column(String(16), default="book", server_default="book")
    # `Document.source_file` / `ingested_file` (base) — file gốc (`source.pdf`) và kết quả bước ingest (`pages.jsonl`)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    ingested_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    pdf_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # cấu hình xử lý của tài liệu (`app/models/document_profile.py::Profile`, dạng JSON; repository đọc/ghi qua Pydantic)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DocumentStage(Base):
    """Trạng thái một bước của một tài liệu. Vòng đời: not_started -> running -> pending_review -> approved (failed/cancelled/stale)."""

    __tablename__ = "document_stages"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    stage_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="not_started")
    options: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentOverride(Base):
    """Chỉnh sửa tay của người duyệt lên kết quả một bước — tách khỏi kết quả máy để chạy lại bước không mất công sửa."""

    __tablename__ = "document_overrides"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    stage_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
