"""Model LLM cho agent — 1 điểm khởi tạo duy nhất qua `init_chat_model` (LangChain có
sẵn, hỗ trợ cú pháp "provider:model" + mọi kwargs riêng của provider truyền thẳng
xuống), không tự viết wrapper theo từng provider.

`AGENT_MODEL`/`model` truyền vào `get_model()` BẮT BUỘC có tiền tố "<provider>:" —
thiếu tiền tố khiến `init_chat_model` tự suy luận provider từ tên model (vd
"deepseek-v4-flash" tự suy ra provider "deepseek" nhưng KHÔNG qua OpenRouter, gọi thẳng
api.deepseek.com với sai key) — lỗi khó phát hiện, `get_model()` raise rõ ràng ngay lúc
gọi thay vì để lọt qua rồi lỗi runtime khó hiểu lúc gọi model.

3 nhánh provider, mỗi nhánh có kwargs riêng KHÔNG dùng chung được (`thinking_level`/
`include_thoughts` chỉ Gemini hiểu, `extra_body` "thinking" chỉ DeepSeek hiểu...):
  - "openai"   : OpenRouter (API tương thích OpenAI) — model khác của OpenRouter, KHÔNG
    phải OpenAI thật (project không có tài khoản OpenAI).
  - "deepseek" : DeepSeek API trực tiếp (`langchain-deepseek`, đã có trong deps qua
    `langchain[...]`) — cần `DEEPSEEK_API_KEY` thật, KHÔNG dùng chung
    `OPENROUTER_API_KEY` (2 endpoint khác nhau, key không tương thích chéo).
  - còn lại    : Gemini (`google_genai`) — dùng `thinking_level`/`include_thoughts`.

Model chọn theo từng conversation (`Conversation.model`, `AGENT_MODEL_CHOICES` ở
`app/core/config.py`) — `get_model()` được middleware `graph.py::select_model` gọi lại
NHIỀU LẦN/turn (mỗi lần LLM suy nghĩ trong vòng lặp ReAct), nên cache instance theo chuỗi
"provider:model" bằng `lru_cache` thay vì tạo `BaseChatModel` mới mỗi lần (tốn khởi tạo
HTTP client, mất connection pooling reuse)."""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import settings


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
        # `entity_grounding.py`/`critic_review`, `graph.py`) — lỗi thật đã gặp: "Thinking
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
