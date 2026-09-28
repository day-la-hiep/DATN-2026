"""Phát kết quả của 1 turn: event realtime lên Redis (SSE) + `AgentResponseMessage` vào
RabbitMQ để Core persist. Gom vào 1 chỗ vì cả 3 kết cục của turn (xong, tạm dừng hỏi
lại, lỗi) đều đi đúng chuỗi "event -> [DONE] -> publish response" này."""

import json
from typing import Any, Literal

from agent.dto.schemas import AgentResponseMessage, TurnRequest
from app.core.constants import AGENT_RESPONSE_QUEUE, STREAM_DONE_SENTINEL
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import publish as redis_publish


async def emit(channel: str, payload: dict[str, Any]) -> None:
    await redis_publish(channel, json.dumps(payload))


async def finish_turn(
    channel: str,
    req: TurnRequest,
    event: dict[str, Any],
    *,
    content: str,
    status: Literal["done", "question"],
    choice: dict[str, Any] | None = None,
    reasoning: list[dict[str, Any]] | None = None,
) -> None:
    """Kết thúc/tạm dừng turn: phát `event` cuối lên SSE, đóng stream bằng sentinel
    `[DONE]`, rồi báo Core (`agent_response_queue`) để upsert dòng assistant.
    `reasoning` rỗng -> None để Core không ghi đè `Message.extra.reasoning` bằng list rỗng."""
    await emit(channel, event)
    await redis_publish(channel, STREAM_DONE_SENTINEL)
    await rabbitmq_client.publish(
        AGENT_RESPONSE_QUEUE,
        AgentResponseMessage(
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            content=content,
            status=status,
            choice=choice,
            reasoning=reasoning or None,
        )
        .model_dump_json()
        .encode("utf-8"),
    )
