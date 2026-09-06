"""Conversation — 1 cuộc hội thoại của 1 user (`docs/db-diagram.md` mục 1)."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    # 64 (không phải 36 = độ dài UUID trần) vì `new_conversation_id()` (`app/core/ids.py`)
    # sinh id có tiền tố resource (`conv-<uuid4>` = 41 ký tự).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), default="")
    # default/onupdate Python-side (SQLAlchemy tự tính trước khi INSERT/UPDATE) —
    # không dùng server_default để có giá trị ngay sau flush(), không cần RETURNING.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
