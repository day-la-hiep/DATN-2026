"""Redis dùng chung"""
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager

import redis
import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from app.config.settings import settings


class RedisClient:
    def __init__(self, host: str, port: int, db: int = 0) -> None:
        self._host, self._port, self._db = host, port, db
        self._async: aioredis.Redis | None = None
        self._sync: redis.Redis | None = None

    @classmethod
    def from_settings(cls) -> "RedisClient":
        return cls(settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)

    @property
    def client(self) -> aioredis.Redis:
        if self._async is None:
            self._async = aioredis.Redis(host=self._host, port=self._port, db=self._db, decode_responses=True)
        return self._async

    @property
    def sync_client(self) -> redis.Redis:
        if self._sync is None:
            self._sync = redis.Redis(host=self._host, port=self._port, db=self._db)
        return self._sync

    async def close(self) -> None:
        if self._async is not None:
            await self._async.aclose()
            self._async = None
        if self._sync is not None:
            self._sync.close()
            self._sync = None

    # ----- Pub/Sub -----
    async def publish(self, channel: str, message: str) -> int:
        """Publish message tới 1 channel, trả về số subscriber đã nhận."""
        return await self.client.publish(channel, message)  # type: ignore[no-any-return]

    def pubsub(self) -> PubSub:
        """PubSub thô cho caller cần tự điều khiển subscribe -> việc khác -> listen (vd SSE: subscribe xong mới flush turn)."""
        return self.client.pubsub()

    async def subscribe(self, *channels: str) -> AsyncIterator[dict[str, object]]:
        """Lắng nghe 1 hoặc nhiều channel cố định, yield từng message nhận được."""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(*channels)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield message
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()

    async def psubscribe(self, *patterns: str) -> AsyncIterator[dict[str, object]]:
        """Lắng nghe theo pattern (vd 'agent:events:*'), yield từng message nhận được."""
        pubsub = self.client.pubsub()
        await pubsub.psubscribe(*patterns)
        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    yield message
        finally:
            await pubsub.punsubscribe(*patterns)
            await pubsub.aclose()

    # ----- key/value -----
    async def get(self, key: str) -> str | None:
        return await self.client.get(key)  # type: ignore[no-any-return]

    async def set_value(self, key: str, value: str, *, ex_seconds: int | None = None) -> None:
        await self.client.set(key, value, ex=ex_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def get_del(self, key: str) -> str | None:
        """GET + DELETE atomic"""
        return await self.client.getdel(key)  # type: ignore[no-any-return]

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    # ----- khoá phân tán -----
    def lock(self, name: str, *, timeout: int = 30, blocking_timeout: int = 30) -> AbstractContextManager[object]:
        """Khoá phân tán"""
        return self.sync_client.lock(f"lock:{name}", timeout=timeout, blocking_timeout=blocking_timeout)  # type: ignore[return-value]
