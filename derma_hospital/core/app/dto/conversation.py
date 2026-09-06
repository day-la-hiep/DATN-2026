"""DTO cho resource Conversation (`docs/api-doc.md` mục 1)."""
from app.dto.common import CamelModel


class ConversationOutput(CamelModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class CreateConversationInput(CamelModel):
    """Body cho `POST /conversations` — tạo hội thoại kèm tin nhắn đầu tiên
    (`docs/api-doc.md` mục 1.2)."""

    user_id: str
    init_message: str
    title: str | None = None
