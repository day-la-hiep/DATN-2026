"""Truy vấn DB cho `Conversation` (`docs/db-diagram.md` mục 1)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, conversation: Conversation) -> Conversation:
        self._db.add(conversation)
        await self._db.flush()
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self._db.get(Conversation, conversation_id)

    async def list_by_user(self, user_id: str) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
