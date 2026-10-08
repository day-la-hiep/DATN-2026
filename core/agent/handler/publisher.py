"""Phát kết quả của 1 turn"""

import json
from typing import Any, Literal

from agent.dto.schemas import AgentResponseMessage, TurnRequest
from app.config.constants import AGENT_RESPONSE_QUEUE, STREAM_DONE_SENTINEL
from app.api.deps import get_rabbitmq_client, get_redis_client


async def emit(channel: str, payload: dict[str, Any]) -> None:
    await get_redis_client().publish(channel, json.dumps(payload))


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
    """Kết thúc/tạm dừng turn"""
    await emit(channel, event)
    await get_redis_client().publish(channel, STREAM_DONE_SENTINEL)
    await get_rabbitmq_client().publish(
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
