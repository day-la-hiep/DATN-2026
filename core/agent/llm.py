"""Model LLM cho agent"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config.settings import settings


def get_model(model: str | None = None) -> BaseChatModel:
    """`model` rỗng/None -> dùng `settings.AGENT_MODEL` (fallback toàn hệ thống)."""
    return _get_model_cached(model or settings.AGENT_MODEL)


@lru_cache
def _get_model_cached(model: str) -> BaseChatModel:
    if ":" not in model:
        raise ValueError(
            f'model="{model}" thiếu tiền tố provider (vd "openai:{model}" cho '
            f'OpenRouter, "deepseek:{model}" cho DeepSeek API trực tiếp) — xem '
            "app/agent/llm.py."
        )
    provider = model.split(":", 1)[0]

    if provider == "openai":
        # OpenRouter: API tương thích OpenAI (`langchain-openai`), chỉ khác base_url +
        # api_key riêng — KHÔNG dùng OPENAI_API_KEY (project không có tài khoản OpenAI).
        return init_chat_model(
            model,
            temperature=settings.AGENT_TEMPERATURE,
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    if provider == "deepseek":
        # `reasoning`/`extra_body` tắt "thinking mode": model reasoning-hybrid của
        # DeepSeek (R1/V3.x trở lên) mặc định BẬT thinking, xung đột với tool_choice ép
        # cứng mà `with_structured_output(method="function_calling")` dùng (xem
        # `hybrid_retrieval/kg.py`/`critic_review`, `graph.py`) — lỗi thật đã gặp: "Thinking
        # mode does not support this tool_choice" (400). Agent này LUÔN cần tool-calling
        # đáng tin cậy nên phải tắt thinking, đổi lấy mất phần suy luận sâu của DeepSeek.
        return init_chat_model(
            model,
            temperature=settings.AGENT_TEMPERATURE,
            api_key=settings.DEEPSEEK_API_KEY,
            extra_body={"thinking": {"type": "disabled"}},
        )

    return init_chat_model(
        model,
        temperature=settings.AGENT_TEMPERATURE,
        thinking_level=settings.AGENT_THINKING_LEVEL,
        # Bắt buộc để provider TRẢ VỀ nội dung "thinking" (Gemini tự tóm tắt suy nghĩ
        # thành các đoạn ngắn) — `thinking_level` chỉ bật suy luận nội bộ, không tự trả
        # về nếu thiếu `include_thoughts`. Dùng làm dòng tóm tắt "đang làm gì" hiển thị
        # cho người dùng (event `message.thinking`, `graph.py::emit_reasoning_step`).
        include_thoughts=True,
    )
