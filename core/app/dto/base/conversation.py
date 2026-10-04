from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.common.constant import ConsultationStatus, MessageSender, MessageType
from app.dto.base.file import File
from app.dto.base.user import Doctor, PatientProfile
from app.dto.base.video_call import VideoCall

# loại tin mốc phiên tư vấn -> trạng thái phiên tại mốc đó và người được phép tạo tin
_CONSULTATION_EVENTS: dict[MessageType, tuple[ConsultationStatus, MessageSender]] = {
    MessageType.CONSULTATION_REQUESTED: (ConsultationStatus.PENDING, MessageSender.PATIENT),
    MessageType.CONSULTATION_ACCEPTED: (ConsultationStatus.ACTIVE, MessageSender.DOCTOR),
    MessageType.CONSULTATION_RESOLVED: (ConsultationStatus.RESOLVED, MessageSender.DOCTOR),
}


class Conversation(BaseModel):
    """Cuộc chat của bệnh nhân. `message` là một luồng chung cho cả AI lẫn bác sĩ (phân biệt bằng `Message.sender`);
    bác sĩ chỉ tham gia trong khoảng của một `ConsultationSession`, người dùng vẫn chat AI tiếp song song."""

    patient: PatientProfile
    message: list[Message]
    consultation_sessions: list[ConsultationSession] = []


class ConsultationSession(BaseModel):
    """Mốc đánh dấu một lần bệnh nhân nhờ bác sĩ hỗ trợ — không chứa tin nhắn. Tin trao đổi nằm trong
    `Conversation.message`; ba mốc yêu cầu/nhận/đóng hiện thành tin `CONSULTATION_*` trong luồng đó.

    Bác sĩ xem được luồng chat từ đầu tới tin `CONSULTATION_RESOLVED` của phiên (phiên còn mở: tới hiện tại)."""

    doctor: Doctor | None = None  # None khi chưa có bác sĩ nhận
    status: ConsultationStatus = ConsultationStatus.PENDING
    reason: str
    requested_at: datetime | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status != ConsultationStatus.PENDING and self.doctor is None:
            raise ValueError("doctor is required when status is active or resolved")
        if self.status == ConsultationStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved_at is required when status is resolved")
        return self


class Message(BaseModel):
    sender: MessageSender
    content: str
    metadata: MessageMetadata

    @model_validator(mode="after")
    def validate_sender(self):
        event = _CONSULTATION_EVENTS.get(self.metadata.message_type)
        if event is not None and self.sender != event[1]:
            raise ValueError(f"{self.metadata.message_type.value} must be sent by {event[1].value}")
        return self


class MessageMetadata(BaseModel):
    message_type: MessageType
    attached_files: list[File]
    consultation_session: ConsultationSession | None  # bắt buộc với tin mốc CONSULTATION_*
    video_call: VideoCall | None

    @model_validator(mode="after")
    def validate_metadata(self):
        event = _CONSULTATION_EVENTS.get(self.message_type)
        if event is not None:
            if self.consultation_session is None:
                raise ValueError(f"consultation_session is required for {self.message_type.value}")
            if self.consultation_session.status != event[0]:
                raise ValueError(
                    f"consultation_session.status must be {event[0].value} for {self.message_type.value}"
                )
        if self.message_type == MessageType.VIDEO_CALL:
            if self.video_call is None:
                raise ValueError("video_call is required for VIDEO_CALL")

        return self
