"""Khởi tạo chat model dùng cho agent (qua LangChain `init_chat_model`).

`AGENT_MODEL` theo cú pháp "provider:model" (vd "openai:gpt-4o-mini",
"google_genai:gemini-2.0-flash"...). Cần cài thêm package tích hợp tương ứng,
vd: `uv add langchain-openai` hoặc `uv add langchain-google-genai`, và set API
key của provider đó (vd `OPENAI_API_KEY`) trong `.env`.
"""
from collections.abc import Sequence
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from app.core.config import settings


@lru_cache
def get_llm() -> BaseChatModel:
    """Chat model "trần" (chưa bind tool), cấu hình từ `.env` (`AGENT_MODEL`,
    `AGENT_TEMPERATURE`). Cache theo process vì `init_chat_model` không rẻ và
    model dùng chung cho mọi node reasoning."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(
        settings.AGENT_MODEL,
        temperature=settings.AGENT_TEMPERATURE,
    )


def get_llm_with_tools(tools: Sequence[BaseTool]) -> Runnable:
    """Bind tool vào chat model — dùng khi thêm node "act" xử lý tool-calling
    (xem README, phần Agent). Không cache vì bộ tool có thể khác nhau theo
    ngữ cảnh gọi (mỗi node/luồng có thể cần 1 tập tool riêng)."""
    return get_llm().bind_tools(list(tools))
