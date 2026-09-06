"""Business logic cho Conversation (`docs/api-doc.md` mục 1)."""
from app.core.ids import new_conversation_id
from app.dto.conversation import ConversationOutput, CreateConversationInput
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.services.message_service import MessageService


class ConversationService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_service: MessageService,
    ) -> None:
        self._conversations = conversation_repository
        self._messages = message_service

    async def list_conversations(self, user_id: str) -> list[ConversationOutput]:
        conversations = await self._conversations.list_by_user(user_id)
        return [_to_output(c) for c in conversations]

    async def create_conversation(
        self, body: CreateConversationInput
    ) -> ConversationOutput:
        """Tạo hội thoại + lưu `initMessage` (nếu có) + publish turn đầu tiên — quyết định
        thiết kế ở `docs/api-doc.md` mục 1.2 (FE chỉ cần 1 request).

        Chỉ mở turn khi `init_message` thực sự có nội dung: FE (`store.ts`) luôn tạo
        conversation với `initMessage=""` rồi gọi `POST .../messages` riêng cho tin đầu
        tiên (tránh trùng lặp) — mở turn với content rỗng vừa vô nghĩa vừa khiến LLM
        (Gemini) từ chối request, để lại Redis "active_turn" key treo vĩnh viễn vì turn
        không bao giờ hoàn tất."""
        conversation = Conversation(
            id=new_conversation_id(),
            user_id=body.user_id,
            title=body.title or "",
        )
        await self._conversations.create(conversation)

        if body.init_message.strip():
            await self._messages.start_new_turn(
                conversation_id=conversation.id, content=body.init_message
            )
        return _to_output(conversation)


def _to_output(conversation: Conversation) -> ConversationOutput:
    return ConversationOutput(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )
