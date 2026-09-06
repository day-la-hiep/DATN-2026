"""Provider DI (FastAPI `Depends`) — dựng cây service/repository theo `AsyncSession`
request-scoped (`docs/quy-uoc.md` mục 4)."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService


def get_message_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageService:
    return MessageService(MessageRepository(db))


def get_conversation_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    message_service: Annotated[MessageService, Depends(get_message_service)],
) -> ConversationService:
    return ConversationService(ConversationRepository(db), message_service)
