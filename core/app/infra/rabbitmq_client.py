"""RabbitMQ client dùng chung (aio-pika), quản lý 1 connection/channel cho cả app.

Vòng đời: gọi connect() lúc app startup (FastAPI lifespan), close() lúc shutdown.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from app.core.config import settings

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class RabbitMQClient:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.RABBITMQ_URL
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        if self._connection is not None:
            await self._connection.close()

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    @property
    def channel(self) -> AbstractChannel:
        if self._channel is None:
            raise RuntimeError("RabbitMQ chưa connect — gọi connect() trước.")
        return self._channel

    async def declare_queue(self, name: str, *, durable: bool = True) -> AbstractQueue:
        return await self.channel.declare_queue(name, durable=durable)

    async def publish(
        self, queue: str, body: bytes, *, persistent: bool = True
    ) -> None:
        """Publish message vào 1 queue (declare queue nếu chưa tồn tại)."""
        await self.declare_queue(queue)
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                delivery_mode=(
                    aio_pika.DeliveryMode.PERSISTENT
                    if persistent
                    else aio_pika.DeliveryMode.NOT_PERSISTENT
                ),
                content_type="application/json",
            ),
            routing_key=queue,
        )

    async def consume(self, queue: str, handler: MessageHandler) -> None:
        """Đăng ký consumer cho 1 queue. handler nên tự `async with message.process()`."""
        q = await self.declare_queue(queue)
        await q.consume(handler)


rabbitmq_client = RabbitMQClient()
