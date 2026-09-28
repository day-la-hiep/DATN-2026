"""Message — tin nhắn user/assistant (`docs/db-diagram.md` mục 1–2).

`extra` map sang cột DB tên `metadata` — KHÔNG đặt attribute Python là `metadata`
(trùng tên reserved `Base.metadata` của SQLAlchemy, xem `docs/db-diagram.md` mục 2).
"""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Message(Base):
    __tablename__ = "messages"

    # 64 (không phải 36 = độ dài UUID trần) vì `new_message_id()` (`app/core/ids.py`)
    # sinh id có tiền tố resource (`msg-<uuid4>` = 40 ký tự).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    # role: "user" | "assistant"; status: "pending" | "queued" | "streaming" | "done" | "question"
    # — String (không Postgres ENUM) để dễ thêm giá trị mới, xem docs/db-diagram.md mục 4.
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    extra: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
