from agent.context.agent_context import AgentContext
from agent.dto.schemas import TurnRequest
from app.api.deps import get_postgres_client
from app.config.settings import settings
from app.repositories.conversation_repository import ConversationRepository


async def _conversation_for(conversation_id: str) -> tuple[str, str]:
    async with get_postgres_client().session_factory() as db:
        repo = ConversationRepository(db)
        conversation = await repo.get(conversation_id)
        if conversation is None:
            return "", ""
        user_id = await repo.owner_user_id(conversation) or ""
    model = settings.AGENT_MODEL_CHOICES.get(conversation.model, "")
    return user_id, model


async def build_context(req: TurnRequest) -> AgentContext:
    user_id, model = await _conversation_for(req.conversation_id)
    return AgentContext(
        user_id=user_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[
            a.storage_key
            for a in (req.attached_files or [])
            if a.content_type.startswith("image/")
        ],
        model=model,
    )
