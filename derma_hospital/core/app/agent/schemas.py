"""Message contract Core (FastAPI) ⇄ Agent Worker qua RabbitMQ (2 queue,
`app/core/constants.py`).

`TurnRequest`: Core -> Worker (`agent_request_queue`) — mở turn mới/Steer (`type="turn"`)
hoặc resume câu hỏi `ask_user` đang chờ (`type="resume"`, xem `app/agent/tools.py`).

`AgentResponseMessage`: Worker -> Core (`agent_response_queue`) — Core là writer duy
nhất của bảng `messages`, tự upsert khi nhận được (`app/agent/response_consumer.py`).
"""
from typing import Any, Literal

from pydantic import BaseModel


class TurnAttachment(BaseModel):
    """1 ảnh đính kèm turn — `object_key` là key MinIO (`app/infra/file_storage.py`,
    trùng `FileAttachmentDto.id`), Worker tự fetch bytes qua `get_object_bytes()` khi
    tool `classify_skin_image` (`app/agent/tools/skin_image_classifier.py`) cần."""

    name: str
    type: str
    object_key: str


class TurnRequest(BaseModel):
    type: Literal["turn", "resume"]
    conversation_id: str
    message_id: str  # id assistant message của turn (ổn định qua mọi resume)
    corr_id: str | None = None
    content: str | None = None  # bắt buộc khi type="turn" (turn mới hoặc Steer)
    is_steer: bool = False
    answer: str | None = None  # bắt buộc khi type="resume" — câu trả lời cho `ask_user`
    attachments: list[TurnAttachment] | None = None


class AgentResponseMessage(BaseModel):
    conversation_id: str
    message_id: str
    content: str
    status: Literal["done", "question"]
    # `MessageChoiceDto.model_dump(mode="json", by_alias=True)` — chỉ set khi
    # status="question" (`app/dto/message.py`).
    choice: dict[str, Any] | None = None
