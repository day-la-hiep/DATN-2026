from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    __tablename__ = "messages"

    # DB sinh id (`gen_random_uuid()`); tin cũ giữ id dạng `msg-<uuid>` nên cột vẫn là chuỗi 64
    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    # sender: `MessageSender` ("patient" | "ai" | "doctor"); status: "pending" | "queued" | "streaming" | "done" | "question"
    # — String (không Postgres ENUM) để dễ thêm giá trị mới, xem docs/db-diagram.md mục 4.
    sender: Mapped[str] = mapped_column(String(20))
    # `MessageType` — cột riêng (không chỉ trong `metadata`) để lọc/đếm theo loại tin
    message_type: Mapped[str] = mapped_column(String(32), default="text", server_default="text")
    # chỉ điền cho tin `message_type="video_call"` (`MessageMetadata.video_call` của base)
    video_call_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_calls.id", ondelete="SET NULL"), default=None
    )
    # chỉ điền cho 3 tin mốc `consultation_*`: tin mốc thuộc phiên tư vấn nào
    consultation_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="SET NULL"), index=True, default=None
    )
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20))
    extra: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
