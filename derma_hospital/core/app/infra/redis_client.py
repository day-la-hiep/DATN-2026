"""Redis client dùng chung + helper cho Pub/Sub.

Dùng cho realtime event (vd: forward sự kiện agent -> SSE client) theo pattern:
  - publish(channel, message)      : bên gửi sự kiện
  - subscribe(*channels)           : lắng nghe kênh cố định
  - psubscribe(*patterns)          : lắng nghe theo pattern (vd "agent:events:*")
"""
from collections.abc import AsyncIterator

import redis.asyncio as redis

from app.core.config import settings

redis_client: redis.Redis = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    decode_responses=True,
)


async def publish(channel: str, message: str) -> int:
    """Publish message tới 1 channel, trả về số subscriber đã nhận."""
    return await redis_client.publish(channel, message)  # type: ignore[no-any-return]


async def subscribe(*channels: str) -> AsyncIterator[dict[str, object]]:
    """Lắng nghe 1 hoặc nhiều channel cố định, yield từng message nhận được."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield message
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()


async def psubscribe(*patterns: str) -> AsyncIterator[dict[str, object]]:
    """Lắng nghe theo pattern (vd 'agent:events:*'), yield từng message nhận được."""
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe(*patterns)
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                yield message
    finally:
        await pubsub.punsubscribe(*patterns)
        await pubsub.aclose()


async def get(key: str) -> str | None:
    return await redis_client.get(key)  # type: ignore[no-any-return]


async def set_value(key: str, value: str, *, ex_seconds: int | None = None) -> None:
    await redis_client.set(key, value, ex=ex_seconds)


async def delete(key: str) -> None:
    await redis_client.delete(key)


async def ping() -> bool:
    return bool(await redis_client.ping())


async def close() -> None:
    await redis_client.aclose()
