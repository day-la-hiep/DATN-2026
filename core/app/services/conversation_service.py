"""Business logic cho Conversation (`docs/api-doc.md` mục 1)."""

from app.config.settings import settings
from app.dto.request.conversation import CreateConversationInput
from app.dto.response.conversation import ConversationOutput
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.patient_profile_repository import PatientProfileRepository
from app.services.message_service import MessageService


class ConversationNotFoundError(Exception):
    pass


class PatientProfileNotFoundError(Exception):
    """Tài khoản chưa có hồ sơ bệnh nhân nào — hội thoại bắt buộc gắn hồ sơ (`Conversation.patient`)."""


class ConversationService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        patient_profile_repository: PatientProfileRepository,
        message_service: MessageService,
    ) -> None:
        self._conversations = conversation_repository
        self._patient_profiles = patient_profile_repository
        self._messages = message_service

    async def list_conversations(
        self, user_id: str
    ) -> list[ConversationOutput]:
        conversations = await self._conversations.list_by_user(user_id)
        return [_to_output(c) for c in conversations]

    async def create_conversation(
        self, body: CreateConversationInput
    ) -> ConversationOutput:
        """Tạo hội thoại + lưu `content`"""
        # API chưa cho chọn hồ sơ -> dùng hồ sơ mặc định (tạo sớm nhất) của tài khoản
        profile = await self._patient_profiles.first_for_user(body.user_id)
        if profile is None:
            raise PatientProfileNotFoundError(body.user_id)
        conversation = Conversation(
            patient_profile_id=profile.id,
            title=body.title or "",
            model=body.model or settings.AGENT_DEFAULT_MODEL_ID,
        )
        await self._conversations.create(conversation)

        if body.content.strip():
            await self._messages.start_new_turn(
                conversation_id=conversation.id, content=body.content
            )
        return _to_output(conversation)

    async def update_model(
        self, conversation_id: str, model: str
    ) -> ConversationOutput:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        conversation = await self._conversations.update_model(
            conversation, model
        )
        return _to_output(conversation)


def _to_output(conversation: Conversation) -> ConversationOutput:
    return ConversationOutput(
        id=conversation.id,
        title=conversation.title,
        model=conversation.model,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )
