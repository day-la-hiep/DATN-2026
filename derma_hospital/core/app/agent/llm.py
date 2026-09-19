"""Model LLM cho agent — 1 điểm khởi tạo duy nhất qua `init_chat_model` (LangChain có
sẵn, hỗ trợ cú pháp "provider:model" + mọi kwargs riêng của provider truyền thẳng
xuống), không tự viết wrapper theo từng provider.

`thinking_level`/`include_thoughts` là tham số riêng của Gemini ("thinking" — provider
`google_genai`), provider khác (vd `openai`, dùng cho OpenRouter/Gemma — xem
`app/core/config.py::AGENT_MODEL`) không hiểu 2 kwargs này -> phải rẽ nhánh theo
provider thay vì truyền cứng cho mọi model."""
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import settings


def get_model() -> BaseChatModel:
    provider = settings.AGENT_MODEL.split(":", 1)[0]

    if provider == "openai":
        # OpenRouter: API tương thích OpenAI (`langchain-openai`), chỉ khác base_url +
        # api_key riêng — KHÔNG dùng OPENAI_API_KEY (project không có tài khoản OpenAI).
        return init_chat_model(
            settings.AGENT_MODEL,
            temperature=settings.AGENT_TEMPERATURE,
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
        )

    return init_chat_model(
        settings.AGENT_MODEL,
        temperature=settings.AGENT_TEMPERATURE,
        thinking_level=settings.AGENT_THINKING_LEVEL,
        # Bắt buộc để provider TRẢ VỀ nội dung "thinking" (Gemini tự tóm tắt suy nghĩ
        # thành các đoạn ngắn) — `thinking_level` chỉ bật suy luận nội bộ, không tự trả
        # về nếu thiếu `include_thoughts`. Dùng làm dòng tóm tắt "đang làm gì" hiển thị
        # cho người dùng (`worker.py::_drive`, event `message.thinking`), KHÔNG cần thêm
        # 1 lệnh gọi LLM riêng để tự tóm tắt.
        include_thoughts=True,
    )
