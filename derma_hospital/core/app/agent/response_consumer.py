"""Consumer `agent_response_queue`, chạy TRONG tiến trình Core (FastAPI, `main.py`
lifespan) — Core là writer duy nhất của bảng `messages`, upsert khi nhận kết quả từ
Agent Worker (`app/agent/worker.py`, tiến trình khác) qua RabbitMQ.
"""
import json

from aio_pika.abc import AbstractIncomingMessage

from app.agent.schemas import AgentResponseMessage
from app.core.constants import AGENT_ACTIVE_TURN_KEY, AGENT_RESPONSE_QUEUE
from app.db.session import AsyncSessionLocal
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import delete as redis_delete
from app.repositories.message_repository import MessageRepository


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            msg = AgentResponseMessage.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[ResponseConsumer] invalid message: {exc}")
            return

        async with AsyncSessionLocal() as db:
            repo = MessageRepository(db)
            await repo.upsert_assistant(
                message_id=msg.message_id,
                conversation_id=msg.conversation_id,
                content=msg.content,
                status=msg.status,
                extra={"choice": msg.choice} if msg.choice is not None else None,
            )
            await db.commit()

        if msg.status == "done":
            # Turn tạm dừng (`status="question"`) vẫn CÒN active — resume tiếp tục CÙNG
            # `message_id`, chỉ xoá key khi turn thật sự kết thúc.
            await redis_delete(AGENT_ACTIVE_TURN_KEY.format(conversation_id=msg.conversation_id))


async def start_consuming() -> None:
    """Đăng ký consumer rồi return ngay (không block) — gọi trong `main.py` lifespan
    TRƯỚC `yield`, an toàn vì `consume()` chỉ đăng ký callback."""
    await rabbitmq_client.consume(AGENT_RESPONSE_QUEUE, _on_message)
