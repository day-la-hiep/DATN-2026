"""Truy vấn DB cho `Message` (`docs/db-diagram.md` mục 1–2).

`upsert_assistant`: insert/update 1 row assistant duy nhất cho cả turn — dùng khi turn
tạm dừng (`status="question"`) và khi kết thúc (`status="done"`,
`app/agent/response_consumer.py`)."""
from datetime import UTC, datetime
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

    async def find_pending_by_question_id(
        self, conversation_id: str, question_id: str
    ) -> Message | None:
        """Tìm assistant message đang `status="question"` có `choice.questionId` khớp
        (dùng cho `POST .../questions/{questionId}/answer`, `docs/api-doc.md` mục 2.2).
        `extra.choice` set trực tiếp — không còn lồng trong `reasoning[]` như bản
        Turn/Step/Reasoning cũ, vì agent hiện tại (`app/agent/graph.py`) chỉ có ĐÚNG 1
        câu hỏi đang chờ tại 1 thời điểm, không phải danh sách Reasoning."""
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
            Message.status == "question",
        )
        result = await self._db.execute(stmt)
        for message in result.scalars().all():
            choice = (message.extra or {}).get("choice") or {}
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
        """Insert nếu chưa có, update nếu đã có — cùng 1 row cho cả turn.

        Với luồng hiện tại Core đã tạo sẵn row assistant (`status="queued"`) lúc
        `POST .../messages` nên đây gần như luôn là UPDATE. Khi turn kết thúc/tạm dừng
        (`done`/`question`) thì **dời `created_at` = now()** để row assistant luôn sắp SAU
        mọi tin Steer user (vốn được tạo GIỮA turn, sau row assistant) — giữ đúng thứ tự
        `Initial User → Steer → Assistant` ở `GET .../messages` (`docs/async-api-doc.md`
        mục 5).
        """
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
        if status in ("done", "question"):
            message.created_at = datetime.now(UTC)
        await self._db.flush()
        return message
