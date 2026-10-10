"""DTO Output cho resource Message"""
from typing import Literal

from pydantic import BaseModel

from app.common.constant import MessageSender, MessageType
from app.dto.base import VideoCall
from app.dto.common import ConsultationSessionDto, FileDto, MessageChoice, Step


class ChatSourceDto(BaseModel):
    """Tài liệu y khoa agent trích dẫn khi trả lời."""

    id: str
    title: str
    citation_key: str
    law_name: str
    url: str | None = None
    content: str


class MessageMetadataDto(BaseModel):
    """Toàn bộ field optional-theo-loại của 1 message"""

    # --- cùng tên với base `MessageMetadata` ---
    message_type: MessageType | None = None
    attached_files: list[FileDto] | None = None  # tệp user upload kèm tin nhắn
    consultation_session: ConsultationSessionDto | None = None  # tin mốc CONSULTATION_*
    video_call: VideoCall | None = None
    # --- riêng của luồng chat ---
    reasoning: list[Step] | None = None  # chỉ tin assistant
    choice: MessageChoice | None = None  # chỉ tin assistant (hỏi lại)
    sources: list[ChatSourceDto] | None = None  # chỉ tin assistant
    is_option_response: bool | None = None  # chỉ tin user (trả lời choice)


class MessageOutput(BaseModel):
    """`sender`, `content`, `metadata` khớp base `Message`; còn lại lấy từ cột bảng `messages`."""

    id: str
    conversation_id: str
    sender: MessageSender
    content: str
    status: Literal["pending", "queued", "streaming", "done", "question"]
    metadata: MessageMetadataDto | None = None
    created_at: str


class SendMessageResult(BaseModel):
    """Response cho `POST /conversations/{id}/messages`"""

    user_message: MessageOutput
    assistant_message: MessageOutput
