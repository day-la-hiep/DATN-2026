"""Bounded context Hội thoại: cuộc chat, tin nhắn (AI / bệnh nhân / bác sĩ), bước lập luận, nguồn trích dẫn."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

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
    # --- chỉ tin của AI ---
    reasoning: list[ReasoningStep] = []
    choice: MessageChoice | None = None  # câu hỏi lại (`ask_user`) đang chờ / đã được trả lời
    sources: list[Source] = []

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


class ChoiceOption(BaseModel):
    id: str
    label: str


class AnsweredChoice(BaseModel):
    option_id: str
    label: str
    custom: bool = False  # người dùng tự nhập thay vì chọn phương án có sẵn


class MessageChoice(BaseModel):
    question_id: str
    question: str
    options: list[ChoiceOption]
    answered: AnsweredChoice | None = None


class ReasoningStep(BaseModel):
    """Một bước lập luận của AI trong một lượt trả lời: tự suy nghĩ, gọi tool, hoặc hỏi lại người dùng."""

    id: str
    title: str
    content: str
    input: Any | None = None  # tham số tool, với bước gọi tool
    status: Literal["processing", "done"]
    type: Literal["default", "tool_call", "tool_ask", "thinking"] = "default"
    choice: MessageChoice | None = None  # với bước `tool_ask`


class Source(BaseModel):
    """Một nguồn tri thức AI dùng làm căn cứ. `reference` là khoá trong kho tương ứng (id chunk Qdrant, id nút Neo4j, URL)."""

    kind: Literal["guideline", "document", "kg", "web"]
    title: str
    reference: str
    url: str | None = None
    content: str = ""  # đoạn trích
