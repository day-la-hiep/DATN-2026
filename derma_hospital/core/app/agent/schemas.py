"""Payload RabbitMQ giữa Core <-> Agent Worker (`agent_request_queue`/`agent_response_queue`).

Dùng chung cho cả 2 tiến trình (Core publish, Agent Worker consume — hoặc ngược lại) nên
đặt tại `app/agent/` thay vì `app/dto/` — đây không phải hợp đồng API công khai, chỉ là
giao ước nội bộ giữa 2 process (xem `docs/async-api-doc.md`).
"""
from typing import Any, Literal

from pydantic import BaseModel


class TurnRequest(BaseModel):
    """`type="turn"`: mở turn mới hoặc Steer (`is_steer`). `type="resume"`: trả lời
    câu hỏi (`tool_ask`) đang chờ — xem `kien-truc-agent.md` mục 3, `api-doc.md` mục 2.2.
    """

    type: Literal["turn", "resume"]
    conversation_id: str
    # id assistant message của TURN (không phải của tin nhắn Steer) — Core sinh sẵn
    # lúc publish turn mới, tái dùng cho mọi Steer/resume thuộc cùng turn đó.
    message_id: str
    corr_id: str | None = None

    # type="turn"
    content: str | None = None
    is_steer: bool = False
    steer_message_id: str | None = None  # id row Steer trong `messages`, để update status

    # type="resume"
    question_id: str | None = None
    answer: dict[str, Any] | None = None


class AgentResponseMessage(BaseModel):
    """Payload `agent_response_queue` (Agent Worker/graph -> Core) — Core là consumer
    duy nhất, làm upsert DB (`docs/async-api-doc.md` mục 6). Agent Worker/`pre_step`
    KHÔNG còn ghi Postgres trực tiếp, chỉ publish message này.

    - `type="assistant_upsert"`: ghi/đè dòng assistant message của cả turn
      (`status="question"` lúc tạm dừng, `"done"` lúc kết thúc — cùng 1 row, khớp
      `MessageRepository.upsert_assistant`).
    - `type="steer_status"`: cập nhật status 1 dòng Steer user message đã tồn tại
      (`"pending"` -> `"queued"`, `kien-truc-agent.md` mục 5).
    """

    type: Literal["assistant_upsert", "steer_status"]
    conversation_id: str
    message_id: str  # id dòng cần upsert/update

    # type="assistant_upsert"
    content: str | None = None
    reasoning: list[dict[str, Any]] | None = None  # [ReasoningResult.model_dump(mode="json"), ...]

    # cả 2 type đều set status ("question"|"done" cho assistant_upsert, "queued" cho steer_status)
    status: Literal["question", "done", "queued"] | None = None
