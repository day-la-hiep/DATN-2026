"""Bounded context Hội thoại: cuộc chat và tin nhắn (AI / bệnh nhân / bác sĩ). Bước lập luận, câu hỏi lại, nguồn trích dẫn của AI không phải
entity lưu bảng riêng nên nằm ở `app/dto/common/chat.py`."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

from app.common.constant import ConsultationStatus, MessageSender, MessageType

if TYPE_CHECKING:
    from app.dto.base.consultation import ConsultationSession, VideoCall
    from app.dto.base.identity import PatientProfile
    from app.dto.base.shared import File


class Conversation(BaseModel):
    """Cuộc chat của bệnh nhân. `message` là một luồng chung cho cả AI lẫn bác sĩ (phân biệt bằng `Message.sender`);
    bác sĩ chỉ tham gia trong khoảng của một `ConsultationSession`, người dùng vẫn chat AI tiếp song song."""

    title: str = ""
    patient: PatientProfile
    message: list[Message]
    consultation_sessions: list[ConsultationSession] = []


# loại tin mốc phiên tư vấn -> trạng thái phiên tại mốc đó và người được phép tạo tin
_CONSULTATION_EVENTS: dict[MessageType, tuple[ConsultationStatus, MessageSender]] = {
    MessageType.CONSULTATION_REQUESTED: (ConsultationStatus.PENDING, MessageSender.PATIENT),
    MessageType.CONSULTATION_ACCEPTED: (ConsultationStatus.ACTIVE, MessageSender.DOCTOR),
    MessageType.CONSULTATION_RESOLVED: (ConsultationStatus.RESOLVED, MessageSender.DOCTOR),
}


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
