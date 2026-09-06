"""Qdrant client dùng chung — lưu long-term memory (vector + payload) của Agent
(`app/agent/memory.py`). Cùng phong cách `redis_client.py`/`rabbitmq_client.py`:
1 client module-level + hàm free-function, không phải class service.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import settings

EMBEDDING_DIM = 768  # models/gemini-embedding-001 (Google), truncated qua
# output_dimensionality — PHẢI khớp app/agent/memory.py::_EMBEDDING_DIM

client = AsyncQdrantClient(url=settings.QDRANT_URL)


async def ensure_collection() -> None:
    """Tạo collection nếu chưa có — gọi 1 lần lúc Agent Worker khởi động (idempotent,
    xem `app/agent/worker.py::main()`)."""
    if not await client.collection_exists(settings.QDRANT_COLLECTION):
        await client.create_collection(
            settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


async def upsert_memory(*, point_id: str, vector: list[float], payload: dict[str, object]) -> None:
    await client.upsert(
        settings.QDRANT_COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )


async def search_memories(
    *, user_id: str, vector: list[float], limit: int = 5, score_threshold: float = 0.5
) -> list[ScoredPoint]:
    """Semantic search, lọc theo `user_id` — dùng chung cho memory trong-hội-thoại lẫn
    xuyên-hội-thoại (không phân biệt nguồn gốc, xem `app/agent/memory.py`)."""
    result = await client.query_points(
        settings.QDRANT_COLLECTION,
        query=vector,
        query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
        limit=limit,
        score_threshold=score_threshold,
    )
    return result.points
