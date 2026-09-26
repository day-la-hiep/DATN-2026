"""Consumer `agent_response_queue`, chạy TRONG tiến trình Core (FastAPI, `main.py`
lifespan) — Core là writer duy nhất của bảng `messages`, upsert khi nhận kết quả từ
Agent Worker (`agent/worker.py`, tiến trình khác) qua RabbitMQ.
"""

import json
from typing import Any

from aio_pika.abc import AbstractIncomingMessage

from agent.dto.schemas import AgentResponseMessage
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

        # `Message.extra` cho row assistant CHỈ gồm 2 field này (`reasoning`/`choice`,
        # xem `MessageMetadataDto` — `attachments`/`selection_ref`/`is_option_response`
        # chỉ áp dụng cho tin nhắn user) — REPLACE toàn bộ `extra` bằng state MỚI NHẤT
        # thay vì merge với giá trị cũ trong DB (`MessageRepository.upsert_assistant`),
        # an toàn vì `AgentContext.reasoning_steps` (`app/agent/worker.py`) đã là danh
        # sách ĐẦY ĐỦ tích luỹ từ đầu turn tới thời điểm này, không phải delta.
        extra: dict[str, Any] = {}
        if msg.reasoning:
            extra["reasoning"] = msg.reasoning
        if msg.choice is not None:
            extra["choice"] = msg.choice

        async with AsyncSessionLocal() as db:
            repo = MessageRepository(db)
            await repo.upsert_assistant(
                message_id=msg.message_id,
                conversation_id=msg.conversation_id,
                content=msg.content,
                status=msg.status,
                extra=extra or None,
            )
            await db.commit()

        if msg.status == "done":
            # Turn tạm dừng (`status="question"`) vẫn CÒN active — resume tiếp tục CÙNG
            # `message_id`, chỉ xoá key khi turn thật sự kết thúc.
            await redis_delete(
                AGENT_ACTIVE_TURN_KEY.format(
                    conversation_id=msg.conversation_id
                )
            )


async def start_consuming() -> None:
    """Đăng ký consumer rồi return ngay (không block) — gọi trong `main.py` lifespan
    TRƯỚC `yield`, an toàn vì `consume()` chỉ đăng ký callback."""
    await rabbitmq_client.consume(AGENT_RESPONSE_QUEUE, _on_message)
