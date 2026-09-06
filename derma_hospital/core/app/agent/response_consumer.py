"""Core-side consumer cho `agent_response_queue` (`docs/async-api-doc.md` mục 6).

Core là **writer duy nhất** của bảng `messages` cho các path này — Agent Worker (và
`pre_step` trong `app/agent/graph.py`) chỉ publish `AgentResponseMessage`
(`app/agent/schemas.py`), không đụng Postgres. Đối xứng với `app/agent/worker.py`'s
`_on_message`/`main()` (consumer phía Worker cho `agent_request_queue`), nhưng module
này chạy trong tiến trình Core (`core/main.py` lifespan), không phải Worker.
"""
import json

from aio_pika.abc import AbstractIncomingMessage

from app.agent.schemas import AgentResponseMessage
from app.core.constants import AGENT_ACTIVE_TURN_KEY, AGENT_RESPONSE_QUEUE
from app.db.session import AsyncSessionLocal
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import delete as redis_delete
from app.repositories.message_repository import MessageRepository


async def _on_response(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            msg = AgentResponseMessage.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[Response Consumer] invalid payload: {exc}")
            return

        async with AsyncSessionLocal() as db:
            repo = MessageRepository(db)
            if msg.type == "assistant_upsert":
                await repo.upsert_assistant(
                    message_id=msg.message_id,
                    conversation_id=msg.conversation_id,
                    content=msg.content or "",
                    status=msg.status or "done",
                    extra={"reasoning": msg.reasoning or []},
                )
            else:
                await repo.update_status(msg.message_id, msg.status or "queued")
            await db.commit()

        # Turn thực sự kết thúc (không phải tạm dừng chờ tool_ask) -> dọn Redis
        # active-turn key ở đây (Core là bên đã SET key này lúc publish turn, xem
        # `app/services/message_service.py::start_new_turn`).
        if msg.type == "assistant_upsert" and msg.status == "done":
            await redis_delete(AGENT_ACTIVE_TURN_KEY.format(conversation_id=msg.conversation_id))


async def start_consuming() -> None:
    """Đăng ký consumer cho `agent_response_queue` — gọi 1 lần lúc Core khởi động
    (`core/main.py` lifespan), sau `rabbitmq_client.connect()`."""
    await rabbitmq_client.consume(AGENT_RESPONSE_QUEUE, _on_response)
