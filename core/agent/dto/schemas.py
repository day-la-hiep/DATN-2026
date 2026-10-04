"""Message contract Core (FastAPI) ⇄ Agent Worker qua RabbitMQ (2 queue,
`app/config/constants.py`).

`TurnRequest`: Core -> Worker (`agent_request_queue`) — mở turn mới (`type="turn"`)
hoặc resume câu hỏi `ask_user` đang chờ (`type="resume"`, xem `agent/tools/ask_user.py`).

`AgentResponseMessage`: Worker -> Core (`agent_response_queue`) — Core là writer duy
nhất của bảng `messages`, tự upsert khi nhận được (`agent/handler/response_consumer.py`).
"""
from typing import Any, Literal

from pydantic import BaseModel


class TurnAttachment(BaseModel):
    """1 ảnh đính kèm turn — field khớp `app/dto/base/file.py::File`; `storage_key` là key MinIO
    (`app/services/file_store_service.py`), Worker tự fetch bytes qua `get_object_bytes()` khi
    tool `classify_skin_image` (`agent/tools/skin_image_classifier.py`) cần."""

    file_name: str
    content_type: str
    storage_key: str


class TurnRequest(BaseModel):
    type: Literal["turn", "resume"]
    conversation_id: str
    message_id: str  # id assistant message của turn (ổn định qua mọi resume)
    corr_id: str | None = None
    content: str | None = None  # bắt buộc khi type="turn"
    answer: str | None = None  # bắt buộc khi type="resume" — câu trả lời cho `ask_user`
    attached_files: list[TurnAttachment] | None = None


class AgentResponseMessage(BaseModel):
    conversation_id: str
    message_id: str
    content: str
    status: Literal["done", "question"]
    # `MessageChoiceDto.model_dump(mode="json")` — chỉ set khi
    # status="question" (`app/dto/response/message.py`).
    choice: dict[str, Any] | None = None
    # `AgentContext.reasoning_steps` tích luỹ được tới thời điểm turn kết thúc/tạm dừng
    # (`agent/state/context.py`, `agent/worker.py::_drive`) — mỗi dict khớp field của
    # `ReasoningStepDto` (`app/dto/response/message.py`). Core persist NGUYÊN list này vào
    # `Message.extra.reasoning` (`agent/handler/response_consumer.py`) để `GET
    # .../messages` trả lại được các bước suy luận sau khi reload, không chỉ thấy lúc
    # đang stream qua SSE (Redis Pub/Sub không replay).
    reasoning: list[dict[str, Any]] | None = None
