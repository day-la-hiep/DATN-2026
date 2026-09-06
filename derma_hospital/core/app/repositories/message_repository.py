"""Truy vấn DB cho `Message` (`docs/db-diagram.md` mục 1–2).

Bao gồm 2 thao tác đặc thù theo `docs/async-api-doc.md` mục 5–6:
  - `list_pending_steers`: `pre_step` (Agent) đọc để biết có Steer nào đang chờ append.
  - `upsert_assistant`: insert/update 1 row assistant duy nhất cho cả turn — dùng khi
    turn tạm dừng (`status="question"`) và khi kết thúc (`status="done"`).
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, message: Message) -> Message:
        self._db.add(message)
        await self._db.flush()
        return message

    async def get(self, message_id: str) -> Message | None:
        return await self._db.get(Message, message_id)

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_steers(self, conversation_id: str) -> list[Message]:
        """Tin nhắn Steer `status="pending"` — chưa được `pre_step` append vào context."""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.status == "pending",
            )
            .order_by(Message.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, message_id: str, status: str) -> None:
        message = await self.get(message_id)
        if message is not None:
            message.status = status
            await self._db.flush()

    async def find_pending_by_question_id(
        self, conversation_id: str, question_id: str
    ) -> Message | None:
        """Tìm assistant message đang `status="question"` chứa `choice.questionId` khớp
        (dùng cho `POST .../questions/{questionId}/answer`, `docs/api-doc.md` mục 2.2)."""
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.status == "question",
        )
        result = await self._db.execute(stmt)
        for message in result.scalars().all():
            reasoning = (message.extra or {}).get("reasoning") or []
            for step in reasoning:
                choice = step.get("choice") or {}
                if choice.get("questionId") == question_id:
                    return message
        return None

    async def upsert_assistant(
        self,
        *,
        message_id: str,
        conversation_id: str,
        content: str,
        status: str,
        extra: dict[str, Any] | None,
    ) -> Message:
        """Insert nếu chưa có, update nếu đã có — cùng 1 row cho cả turn."""
        message = await self.get(message_id)
        if message is None:
            message = Message(
                id=message_id,
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                status=status,
                extra=extra,
            )
            self._db.add(message)
        else:
            message.content = content
            message.status = status
            message.extra = extra
        await self._db.flush()
        return message
