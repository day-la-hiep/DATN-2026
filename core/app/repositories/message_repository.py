"""Truy vấn DB cho `Message` (`docs/db-diagram.md` mục 1–2).

`upsert_assistant`: insert/update 1 row assistant duy nhất cho cả turn — dùng khi turn
tạm dừng (`status="question"`) và khi kết thúc (`status="done"`,
`agent/handler/response_consumer.py`)."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.video_call import VideoCall


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, message: Message) -> Message:
        self._db.add(message)
        await self._db.flush()
        return message

    async def video_calls(self, messages: list[Message]) -> dict[str, VideoCall]:
        """Cuộc gọi video của các tin `video_call` trong 1 truy vấn (theo `video_call_id`)."""
        ids = [m.video_call_id for m in messages if m.video_call_id]
        if not ids:
            return {}
        return {v.id: v for v in await self._db.scalars(select(VideoCall).where(VideoCall.id.in_(ids)))}

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
        """Tìm tin AI đang `status="question"` có `choice.question_id` khớp
        (dùng cho `POST .../questions/{question_id}/answer`, `docs/api-doc.md` mục 2.2).
        `extra.choice` set trực tiếp — không còn lồng trong `reasoning[]` như bản
        Turn/Step/Reasoning cũ, vì agent hiện tại (`agent/graph/chat_graph.py`) chỉ có ĐÚNG 1
        câu hỏi đang chờ tại 1 thời điểm, không phải danh sách Reasoning."""
        stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sender == "ai",
            Message.status == "question",
        )
        result = await self._db.execute(stmt)
        for message in result.scalars().all():
            choice = (message.extra or {}).get("choice") or {}
            if choice.get("question_id") == question_id:
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
        `POST .../messages` nên đây gần như luôn là UPDATE.
        """
        message = await self.get(message_id)
        if message is None:
            message = Message(
                id=message_id,
                conversation_id=conversation_id,
                sender="ai",
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
