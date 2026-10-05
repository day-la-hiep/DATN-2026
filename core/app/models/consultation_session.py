"""ConsultationSession — mốc một lần bệnh nhân nhờ bác sĩ hỗ trợ (`app/dto/base/consultation.py::ConsultationSession`).
Không chứa tin nhắn: tin trao đổi nằm trong `messages` của hội thoại (`sender="doctor"`); 3 mốc yêu cầu/nhận/đóng là tin
`message_type="consultation_*"` trỏ về phiên qua `messages.consultation_session_id`."""
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConsultationSession(Base):
    __tablename__ = "consultation_sessions"
    __table_args__ = (
        # trùng validator của base — chặn cả khi ghi DB không qua DTO
        CheckConstraint("status = 'pending' OR doctor_id IS NOT NULL", name="doctor_when_not_pending"),
        CheckConstraint("status <> 'resolved' OR resolved_at IS NOT NULL", name="resolved_at_when_resolved"),
        # tối đa 1 phiên đang mở / hội thoại: tin bác sĩ gắn với phiên theo khoảng thời gian, 2 phiên mở sẽ không phân biệt được
        Index(
            "uq_consultation_sessions_open_per_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
            sqlite_where=text("status <> 'resolved'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    # FK tới `doctors` (không phải `users`) để DB chặn gán người không phải bác sĩ
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    # `ConsultationStatus`: "pending" | "active" | "resolved"
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    reason: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
