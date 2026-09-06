"""DTO cho resource Message — request/response API + shape `metadata` JSONB.

Nguồn chuẩn field: `fe/features/chat/types.ts`. Xem `docs/api-doc.md` mục 2–3 và
`docs/db-diagram.md` mục 2 (quy ước JSONB `metadata`).
"""
from typing import Literal

from app.dto.common import CamelModel


class ChoiceOptionDto(CamelModel):
    id: str
    label: str


class AnsweredChoiceDto(CamelModel):
    option_id: str
    label: str
    custom: bool = False


class MessageChoiceDto(CamelModel):
    """Câu hỏi agent đưa ra (`tool_ask`, xem `kien-truc-agent.md` mục 3)."""

    question_id: str
    question: str
    options: list[ChoiceOptionDto]
    answered: AnsweredChoiceDto | None = None


class MessageAnswerDto(CamelModel):
    """Body cho `POST .../questions/{questionId}/answer` (`api-doc.md` mục 2.2)."""

    question_id: str
    option_id: str
    label: str
    custom: bool = False


class ReasoningStepDto(CamelModel):
    """1 Reasoning đã hoàn tất — lưu trong `MessageMetadataDto.reasoning` khi
    `message.done`/`status="question"` (xem `kien-truc-agent.md` mục 1)."""

    id: str
    title: str
    content: str
    status: Literal["processing", "done"]
    type: Literal["default", "tool_call", "tool_ask"] = "default"
    choice: MessageChoiceDto | None = None


class MessageSelectionRefDto(CamelModel):
    """Đoạn tin nhắn user bôi đen để hỏi (quote-then-ask)."""

    source: Literal["message"] = "message"
    ref_id: str
    text: str
    start: int | None = None
    end: int | None = None


class FileAttachmentDto(CamelModel):
    """Metadata tệp user upload kèm tin nhắn (nội dung file không đi qua đây)."""

    id: str
    name: str
    size: int
    type: str


class ChatSourceDto(CamelModel):
    """Tài liệu y khoa agent trích dẫn khi trả lời."""

    id: str
    title: str
    citation_key: str
    law_name: str
    url: str | None = None
    content: str


class MessageMetadataDto(CamelModel):
    """Toàn bộ field optional-theo-loại của 1 message — map 1-1 vào cột
    `messages.metadata` (JSONB). KHÔNG field nào bắt buộc; message text đơn giản
    thì toàn bộ đều `None` (xem `docs/db-diagram.md` mục 2)."""

    reasoning: list[ReasoningStepDto] | None = None  # chỉ tin assistant
    selection_ref: MessageSelectionRefDto | list[MessageSelectionRefDto] | None = None
    attachments: list[FileAttachmentDto] | None = None  # tệp user upload kèm tin nhắn
    choice: MessageChoiceDto | None = None  # chỉ tin assistant (hỏi lại)
    sources: list[ChatSourceDto] | None = None  # chỉ tin assistant
    is_option_response: bool | None = None  # chỉ tin user (trả lời choice)


class MessageOutput(CamelModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "queued", "streaming", "done", "question"]
    metadata: MessageMetadataDto | None = None
    created_at: str


class SendMessageInput(CamelModel):
    """Body cho `POST /conversations/{id}/messages` (`api-doc.md` mục 2.1).

    KHÔNG có field `answer` — trả lời câu hỏi agent đi qua endpoint riêng
    (`docs/async-api-doc.md` mục 4), không phải tin nhắn mới.
    """

    client_message_id: str
    content: str
    model_id: str | None = None
    attachments: list[FileAttachmentDto] | None = None
    selection: MessageSelectionRefDto | list[MessageSelectionRefDto] | None = None
