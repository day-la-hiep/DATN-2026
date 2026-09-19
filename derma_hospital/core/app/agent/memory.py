"""Long-term memory — dùng thẳng `langgraph.store` (`BaseStore`) thay vì tự viết client
wrapper + business logic riêng cho semantic search (khác quyết định cũ, xem
`kien-truc-memory.md` mục 3 — nay ưu tiên framework có sẵn trước, chỉ tự viết phần
LangGraph không có sẵn).

`InMemoryStore` (LangGraph, hỗ trợ sẵn semantic search khi cấu hình `index`) đủ cho dev —
giống cách `InMemorySaver` được dùng cho checkpointer (`app/agent/graph.py`). Production
cần store bền vững hơn 1 tiến trình: `langgraph-checkpoint-postgres` có
`AsyncPostgresStore` cùng interface, hoặc tự viết 1 adapter theo `BaseStore` để giữ hạ
tầng Qdrant đã triển khai — chỉ cần đổi `build_memory_store()`, không đụng chỗ khác
(`graph.py`/tool `save_memory` chỉ biết `BaseStore`, không biết backend cụ thể).

Namespace: `(user_id, "memories")` — 1 user 1 namespace duy nhất, không tách theo
`conversation_id` (tinh thần giống bản Qdrant cũ: nhớ xuyên hội thoại, không chỉ trong
1 hội thoại — xem `kien-truc-memory.md` mục 1).

Chỉ chứa phần hạ tầng/store (không phải tool) — tool `save_memory` (agent chủ động ghi)
nằm ở `app/agent/tools/save_memory.py`, dùng lại `MEMORY_NAMESPACE`/`BaseStore` khai báo
ở đây.
"""

import uuid
from langchain.tools import tool, ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.agent.embeddings import EMBEDDING_DIM, LocalEmbeddings

MEMORY_NAMESPACE = "memories"


def build_memory_store() -> BaseStore:
    """1 điểm khởi tạo duy nhất cho long-term memory store — đổi backend ở đây khi lên
    production (xem docstring module). Embedding LOCAL (`app/agent/embeddings.py`,
    sentence-transformers) — KHÔNG cần API key, tách biệt hoàn toàn với `AGENT_MODEL`
    (`app/agent/llm.py`, hiện là OpenRouter/Gemma)."""
    return InMemoryStore(
        index={
            "dims": EMBEDDING_DIM,
            "embed": LocalEmbeddings(),
            "fields": ["content"],
        }
    )


async def search_memories(
    store: BaseStore, user_id: str, query: str, limit: int = 5
) -> list[str]:
    """Semantic search memory liên quan `query` — dùng trong `pre_model_hook`
    (`app/agent/graph.py`) để tự động nạp context đầu mỗi lần gọi LLM, KHÔNG cần agent tự
    gọi tool để nhớ lại (nhớ chủ động, giống hành vi bản Qdrant cũ)."""
    if not query.strip():
        return []
    items = await store.asearch(
        (user_id, MEMORY_NAMESPACE), query=query, limit=limit
    )
    return [str(item.value.get("content", "")) for item in items]


@tool
async def save_memory(content: str, runtime: ToolRuntime) -> str:
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
