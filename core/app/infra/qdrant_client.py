"""Qdrant client dùng chung. Cùng phong cách `redis_client.py`/`rabbitmq_client.py`:
1 client module-level + hàm free-function, không phải class service.

2 nhóm hàm, 2 collection RIÊNG BIỆT trên cùng client:
  - `ensure_collection`/`upsert_memory`/`search_memories`: long-term memory user
    (`settings.QDRANT_COLLECTION`) — hạ tầng cũ, hiện KHÔNG được gọi (xem
    `app/kien-truc-memory.md`, `app/agent/memory.py` đã chuyển sang
    `langgraph.store.InMemoryStore`). Giữ lại, chưa xoá.
  - `ensure_kb_collection`/`upsert_kb_chunks`/`search_kb_chunks`: guideline da liễu
    tĩnh (`settings.QDRANT_KB_COLLECTION`), ingest 1 lần qua
    `data-ingest/01_normalize/scripts/load_knowledge_base.py`, đọc bởi
    `app/agent/tools/knowledge_base_search.py`.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Record,
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


async def existing_kb_point_ids(point_ids: list[str]) -> set[str]:
    """Cho ingest script (`data-ingest/01_normalize/scripts/load_knowledge_base.py`) resume được sau khi
    bị 429 (free-tier embedding quota) giữa chừng — bỏ qua chunk đã ingest thay vì gọi
    lại embedding API cho chunk đã có."""
    if not point_ids:
        return set()
    records = await client.retrieve(
        settings.QDRANT_KB_COLLECTION, ids=point_ids, with_payload=False, with_vectors=False
    )
    return {str(r.id) for r in records}


async def ensure_kb_collection(dim: int) -> None:
    """Tạo collection KB nếu chưa có — gọi bởi `data-ingest/01_normalize/scripts/load_knowledge_base.py`
    (idempotent, an toàn gọi lại nhiều lần khi re-ingest)."""
    if not await client.collection_exists(settings.QDRANT_KB_COLLECTION):
        await client.create_collection(
            settings.QDRANT_KB_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


async def delete_kb_collection() -> None:
    """Xoá sạch collection KB — dùng khi cần re-ingest từ đầu (`--reset` của
    `data-ingest/01_normalize/scripts/load_knowledge_base.py`), vd đổi embedding model/dim. An toàn gọi
    khi collection chưa tồn tại (no-op)."""
    if await client.collection_exists(settings.QDRANT_KB_COLLECTION):
        await client.delete_collection(settings.QDRANT_KB_COLLECTION)


async def upsert_kb_chunks(points: list[PointStruct]) -> None:
    await client.upsert(settings.QDRANT_KB_COLLECTION, points=points)


async def search_kb_chunks(
    *, vector: list[float], limit: int = 3, chunk_type: str | None = None
) -> list[ScoredPoint]:
    """`chunk_type=None`/`"all"` -> không lọc, search trên mọi loại chunk."""
    query_filter = (
        Filter(must=[FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type))])
        if chunk_type and chunk_type != "all"
        else None
    )
    result = await client.query_points(
        settings.QDRANT_KB_COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=limit,
    )
    return result.points


async def get_kb_disease_id_by_dermo_id(dermo_id: str) -> str | None:
    """Cầu nối id-based giữa DermO/PrimeKG (`app/agent/tools/entity_grounding.py`, field
    `dermo.id`) và guideline KB — filter thuần trên payload `dermo_id` (gắn sẵn lúc ingest
    bởi `data-ingest/01_normalize/scripts/04_link_dermo_ids.py`, KHÔNG phải semantic
    search/LLM tự đoán tên bệnh). Trả `disease_id` của chunk đầu tiên khớp (mọi chunk cùng
    1 bệnh chia sẻ `disease_id`, chỉ cần 1) hoặc `None` nếu bệnh đó chưa match được DermO
    term nào lúc ingest — caller nên fallback về `search_kb_chunks` (semantic search) khi
    đó."""
    records, _ = await client.scroll(
        settings.QDRANT_KB_COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="dermo_id", match=MatchValue(value=dermo_id))]
        ),
        limit=1,
        with_payload=["disease_id"],
    )
    if not records or not records[0].payload:
        return None
    return records[0].payload.get("disease_id")


async def get_kb_chunks_by_disease_id(disease_id: str) -> list[Record]:
    """Lấy TOÀN BỘ chunk (tối đa 5: overview/symptoms/differential/advice/risk) của
    ĐÚNG 1 bệnh theo `disease_id` — filter thuần trên payload, KHÔNG cần vector/embedding
    (khác `search_kb_chunks`, vốn semantic search theo câu hỏi tự do). Dùng khi đã biết
    chính xác bệnh cần đào sâu (vd `disease_id` lấy từ kết quả `search_kb_chunks` trước
    đó), tránh gọi lại semantic search nhiều lần với các `chunk_type` khác nhau mà không
    chắc mỗi lần đều trúng cùng 1 bệnh."""
    records, _ = await client.scroll(
        settings.QDRANT_KB_COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="disease_id", match=MatchValue(value=disease_id))]
        ),
        limit=5,
    )
    return records
