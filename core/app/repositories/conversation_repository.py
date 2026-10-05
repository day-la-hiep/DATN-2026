"""Truy vấn DB cho `Conversation` (`docs/db-diagram.md` mục 1)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.patient_profile import PatientProfile


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
            .join(PatientProfile, PatientProfile.id == Conversation.patient_profile_id)
            .where(PatientProfile.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def owner_user_id(self, conversation: Conversation) -> str | None:
        """Tài khoản sở hữu hội thoại — qua hồ sơ bệnh nhân (`patient_profiles.user_id`)."""
        profile = await self._db.get(PatientProfile, conversation.patient_profile_id)
        return profile.user_id if profile else None

    async def update_model(
        self, conversation: Conversation, model: str
    ) -> Conversation:
        conversation.model = model
        await self._db.flush()
        return conversation
