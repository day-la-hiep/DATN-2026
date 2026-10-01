"""Sách giáo khoa của pipeline `book_ingest`: bản ghi sách, trạng thái từng bước, override của người duyệt.

File lớn (PDF, `pages.jsonl`, mục lục, chunk, ảnh trang, nhật ký) vẫn nằm trong MinIO dưới `toc/<book_id>/`; bảng chỉ giữ dữ liệu nhỏ hay
bị sửa đồng thời (Core + thread xử lý) và cần truy vấn. JSON dùng JSONB trên Postgres, JSON thường ở SQLite (test)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(UTC)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    pdf_name: Mapped[str] = mapped_column(String(255), default="")
    pdf_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # cấu hình xử lý của sách (`app/models/book_profile.py::Profile`, dạng JSON)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BookStage(Base):
    """Trạng thái một bước của một sách. Vòng đời: not_started -> running -> pending_review -> approved (failed/cancelled/stale)."""

    __tablename__ = "book_stages"

    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    stage_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default="not_started")
    options: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    progress: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BookOverride(Base):
    """Chỉnh sửa tay của người duyệt lên kết quả một bước — tách khỏi kết quả máy để chạy lại bước không mất công sửa."""

    __tablename__ = "book_overrides"

    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    stage_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
