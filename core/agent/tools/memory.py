import uuid
from typing import Any
from langchain.tools import tool, ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from agent.context.agent_context import AgentContext
from agent.common.embeddings import EMBEDDING_DIM, OpenRouterEmbeddings

MEMORY_NAMESPACE = "memories"


def build_memory_store() -> BaseStore:
    """1 điểm khởi tạo duy nhất cho long-term memory store"""
    return InMemoryStore(
        index={
            "dims": EMBEDDING_DIM,
            "embed": OpenRouterEmbeddings(),
            "fields": ["content"],
        }
    )


async def search_memories(
    store: BaseStore, user_id: str, query: str, limit: int = 5
) -> list[str]:
    """Semantic search memory liên quan `query`"""
    if not query.strip():
        return []
    items = await store.asearch(
        (user_id, MEMORY_NAMESPACE), query=query, limit=limit
    )
    return [str(item.value.get("content", "")) for item in items]


@tool
async def save_memory(
    content: str, runtime: ToolRuntime[AgentContext, Any]
) -> str:
    """Lưu 1 fact đáng nhớ về người dùng (tình trạng da, tiền sử bệnh, thuốc/dị ứng,
    sở thích điều trị...) để dùng lại ở hội thoại sau.

    Chỉ gọi khi có thông tin THẬT SỰ đáng nhớ lâu dài — không gọi cho câu hỏi/trao đổi
    thông thường không cần nhớ lại sau này.
    """
    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    assert runtime.store is not None
    await runtime.store.aput(
        (ctx.user_id, MEMORY_NAMESPACE),
        key=str(uuid.uuid4()),
        value={"content": content, "conversation_id": ctx.conversation_id},
        index=["content"],
    )
    return "Đã lưu."
