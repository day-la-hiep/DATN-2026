"""Tài liệu của pipeline `document_ingest`"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint, Integer, String, Text, text
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
    # `Document.uploaded_by` (base) — chỉ bác sĩ được tải lên; bác sĩ bị xoá thì tài liệu vẫn giữ
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), nullable=True)
    # cấu hình xử lý của tài liệu (`app/models/document_profile.py::Profile`, dạng JSON; repository đọc/ghi qua Pydantic)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class DocumentStage(Base):
    """Trạng thái một bước của một tài liệu"""

    __tablename__ = "document_stages"
    __table_args__ = (UniqueConstraint("document_id", "stage_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    stage_id: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="not_started")
    options: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentOverride(Base):
    """Chỉnh sửa tay của người duyệt lên kết quả một bước"""

    __tablename__ = "document_overrides"

    document_stage_id: Mapped[str] = mapped_column(
        ForeignKey("document_stages.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
