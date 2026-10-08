"""Context riêng cho từng lần chạy graph"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    user_id: str
    conversation_id: str
    # FE cần để gắn event vào đúng tin nhắn đang stream; rỗng khi test không stream.
    message_id: str = ""
    # `classify_skin_image` đối chiếu với danh sách này vì LLM hay chép sai object_key.
    image_keys: list[str] = field(default_factory=list)
    # "provider:model" đã resolve từ `Conversation.model`; rỗng thì `select_model` fallback `settings.AGENT_MODEL`.
    model: str = ""
    # Middleware append trực tiếp; worker giữ cùng reference nên đọc được sau `astream()` để Core lưu lại
    # (SSE không replay được khi load lại hội thoại). Mỗi dict khớp `Step`.
    reasoning_steps: list[dict[str, Any]] = field(default_factory=list)
