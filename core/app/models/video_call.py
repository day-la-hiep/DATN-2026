"""VideoCall — cuộc gọi video thuộc một phiên tư vấn (`app/dto/base/consultation.py::VideoCall`, `ConsultationSession.video_calls`).
Tách bảng (không chỉ nằm trong `messages.metadata`) vì cuộc gọi có vòng đời pending -> ongoing -> ended được cập nhật sau
khi tin nhắn đã tạo. Tin `message_type="video_call"` trỏ tới đây qua `messages.video_call_id`."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VideoCall(Base):
    __tablename__ = "video_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))
    consultation_session_id: Mapped[str] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"), index=True
    )
    room_id: Mapped[str] = mapped_column(String(128), unique=True)
    # "pending" | "ongoing" | "ended"
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
