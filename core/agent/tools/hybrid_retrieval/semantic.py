"""Nhánh semantic: embedding local (`agent/embeddings.py`) -> Qdrant, chunk sách của pipeline `document_ingest`."""
from typing import Any

from agent.embeddings import get_embeddings
from app.api.deps import get_knowledge_base_service


async def semantic_search(query: str, limit: int) -> list[dict[str, Any]]:
    """Payload các chunk gần câu hỏi nhất, theo thứ tự giảm dần; rỗng khi chưa index sách nào."""
    vector = await get_embeddings().aembed_query(query)
    points = await get_knowledge_base_service().search_document_chunks(vector=vector, limit=limit)
    return [p.payload for p in points if p.payload]
