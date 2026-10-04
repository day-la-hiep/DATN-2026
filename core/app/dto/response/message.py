"""DTO Output cho resource Message — cũng là shape của cột `messages.metadata` (JSONB).

Field cùng nghĩa với `app/dto/base/conversation.py::Message`/`MessageMetadata` dùng cùng tên (`content`, `metadata`,
`message_type`, `attached_files`, `support_request`, `video_call`). Phần còn lại là dữ liệu riêng của luồng chat
(`reasoning`, `choice`, `sources`...), base không có. Nguồn chuẩn field phía FE: `fe/services/apiAdapters.ts`."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.common.constant import MessageType
from app.dto.common import FileDto


class ChoiceOptionDto(BaseModel):
    id: str
    label: str


class AnsweredChoiceDto(BaseModel):
    option_id: str
    label: str
    custom: bool = False


class MessageChoiceDto(BaseModel):
    """Câu hỏi agent đưa ra (`tool_ask`, xem `kien-truc-agent.md` mục 3)."""

    question_id: str
    question: str
    options: list[ChoiceOptionDto]
    answered: AnsweredChoiceDto | None = None


class ReasoningStepDto(BaseModel):
    """1 Reasoning đã hoàn tất — lưu trong `MessageMetadataDto.reasoning` khi
    `message.done`/`status="question"` (xem `kien-truc-agent.md` mục 1)."""

    id: str
    title: str
    content: str
    input: Any | None = None
    status: Literal["processing", "done"]
    # "thinking" khớp `ReasoningStepType` phía FE (`fe/features/chat/types.ts`) — bước
    # LLM tự suy nghĩ/tổng hợp trước khi quyết định gọi tool hay trả lời, phát trực tiếp
    # từ `agent/graph/chat_graph.py::_emit_reasoning_step` (KHÔNG có `tool_calls` liên quan).
    type: Literal["default", "tool_call", "tool_ask", "thinking"] = "default"
    choice: MessageChoiceDto | None = None


class ChatSourceDto(BaseModel):
    """Tài liệu y khoa agent trích dẫn khi trả lời."""

    id: str
    title: str
    citation_key: str
    law_name: str
    url: str | None = None
    content: str


class SupportRequestDto(BaseModel):
    """Field khớp `app/dto/base/medical.py::SupportRequest`."""

    reason: str
    status: Literal["open", "resolved"] = "open"
    created_at: datetime | None = None


class VideoCallDto(BaseModel):
    """Field khớp `app/dto/base/video_call.py::VideoCall`."""

    room_id: str
    status: Literal["pending", "ongoing", "ended"]
    started_at: datetime | None = None
    ended_at: datetime | None = None


class MessageMetadataDto(BaseModel):
    """Toàn bộ field optional-theo-loại của 1 message — map 1-1 vào cột `messages.metadata` (JSONB). KHÔNG field nào bắt
    buộc; message text đơn giản thì toàn bộ đều `None` (xem `docs/db-diagram.md` mục 2)."""

    # --- cùng tên với base `MessageMetadata` ---
    message_type: MessageType | None = None
    attached_files: list[FileDto] | None = None  # tệp user upload kèm tin nhắn
    support_request: SupportRequestDto | None = None
    video_call: VideoCallDto | None = None
    # --- riêng của luồng chat ---
    reasoning: list[ReasoningStepDto] | None = None  # chỉ tin assistant
    choice: MessageChoiceDto | None = None  # chỉ tin assistant (hỏi lại)
    sources: list[ChatSourceDto] | None = None  # chỉ tin assistant
    is_option_response: bool | None = None  # chỉ tin user (trả lời choice)


class MessageOutput(BaseModel):
    """`content`, `metadata` khớp base `Message`; còn lại lấy từ cột bảng `messages`."""

    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "queued", "streaming", "done", "question"]
    metadata: MessageMetadataDto | None = None
    created_at: str


class SendMessageResult(BaseModel):
    """Response cho `POST /conversations/{id}/messages` (`api-doc.md` mục 2.1).

    Trả về CẢ 2 row Core vừa persist:
      - `user_message`: tin nhắn user (`status="done"` với turn mới, `"pending"` với Steer).
      - `assistant_message`: row assistant Core tạo sẵn cho turn (`status="queued"`,
        `content=""`) — FE gắn `id` này vào bubble assistant rồi lắng nghe SSE theo đó,
        không cần chờ event `message.started` để biết id. Với Steer, đây là row assistant
        của turn ĐANG chạy (không tạo mới).
    """

    user_message: MessageOutput
    assistant_message: MessageOutput
