"""Truy cập Qdrant cho KB guideline da liễu + phenotype + long-term memory: tên collection, payload và truy vấn đặc thù, xây trên
capability generic của `QdrantVectorClient` (`app/infra/qdrant_client.py`); instance do `app/api/deps.py` tạo.

3 nhóm hàm, 3 collection RIÊNG BIỆT:
  - `ensure_collection`/`upsert_memory`/`search_memories`: long-term memory user (`settings.QDRANT_COLLECTION`) — hạ tầng cũ,
    hiện KHÔNG được gọi (xem `app/kien-truc-memory.md`; memory đã chuyển sang `langgraph.store.InMemoryStore`). Giữ lại, chưa xoá.
  - `*_kb_*`: guideline da liễu tĩnh (`settings.QDRANT_KB_COLLECTION`), ingest 1 lần qua
    `data_ingest/01_normalize/scripts/load_knowledge_base.py`, đọc bởi `agent/tools/knowledge_base_search.py`.
  - `*_phenotype*`: phenotype PrimeKG (`settings.QDRANT_PHENOTYPE_COLLECTION`).
"""
from qdrant_client.models import PointStruct, Record, ScoredPoint

from app.config.settings import settings
from app.infra.qdrant_client import QdrantVectorClient, eq_filter

EMBEDDING_DIM = 768  # models/gemini-embedding-001 (Google), truncated qua
# output_dimensionality — PHẢI khớp agent/memory.py::_EMBEDDING_DIM


class KnowledgeBaseService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

    # ----- long-term memory (không còn dùng) -----
    async def ensure_collection(self) -> None:
        """Tạo collection memory nếu chưa có (idempotent)."""
        await self._qdrant.ensure_collection(settings.QDRANT_COLLECTION, EMBEDDING_DIM)

    async def upsert_memory(self, *, point_id: str, vector: list[float], payload: dict[str, object]) -> None:
        await self._qdrant.upsert_points(settings.QDRANT_COLLECTION, [PointStruct(id=point_id, vector=vector, payload=payload)])

    async def search_memories(self, *, user_id: str, vector: list[float], limit: int = 5, score_threshold: float = 0.5) -> list[ScoredPoint]:
        """Semantic search, lọc theo `user_id` — dùng chung cho memory trong-hội-thoại lẫn xuyên-hội-thoại."""
        return await self._qdrant.search(settings.QDRANT_COLLECTION, vector, limit=limit, query_filter=eq_filter("user_id", user_id),
                                   score_threshold=score_threshold)

    # ----- KB guideline -----
    async def existing_kb_point_ids(self, point_ids: list[str]) -> set[str]:
        """Cho ingest script resume được sau khi bị 429 (free-tier embedding quota) giữa chừng — bỏ qua chunk đã ingest."""
        return await self._qdrant.existing_ids(settings.QDRANT_KB_COLLECTION, point_ids)

    async def ensure_kb_collection(self, dim: int) -> None:
        """Tạo collection KB nếu chưa có (idempotent, an toàn gọi lại khi re-ingest)."""
        await self._qdrant.ensure_collection(settings.QDRANT_KB_COLLECTION, dim)

    async def delete_kb_collection(self) -> None:
        """Xoá sạch collection KB — dùng khi cần re-ingest từ đầu (`--reset`), vd đổi embedding model/dim. No-op khi chưa có."""
        await self._qdrant.delete_collection(settings.QDRANT_KB_COLLECTION)

    async def upsert_kb_chunks(self, points: list[PointStruct]) -> None:
        await self._qdrant.upsert_points(settings.QDRANT_KB_COLLECTION, points)

    async def search_kb_chunks(self, *, vector: list[float], limit: int = 3, chunk_type: str | None = None) -> list[ScoredPoint]:
        """`chunk_type=None`/`"all"` -> không lọc, search trên mọi loại chunk."""
        query_filter = eq_filter("chunk_type", chunk_type) if chunk_type and chunk_type != "all" else None
        return await self._qdrant.search(settings.QDRANT_KB_COLLECTION, vector, limit=limit, query_filter=query_filter)

    async def get_kb_disease_id_by_dermo_id(self, dermo_id: str) -> str | None:
        """Cầu nối id-based giữa DermO/PrimeKG (`agent/tools/entity_grounding.py`, field `dermo.id`) và guideline KB — filter thuần trên
        payload `dermo_id` (gắn sẵn lúc ingest bởi `04_link_dermo_ids.py`, KHÔNG phải semantic search/LLM tự đoán tên bệnh). Trả
        `disease_id` của chunk đầu tiên khớp hoặc `None` nếu bệnh đó chưa match được DermO term nào lúc ingest — caller nên fallback về
        `search_kb_chunks` (semantic search) khi đó."""
        records = await self._qdrant.scroll(settings.QDRANT_KB_COLLECTION, eq_filter("dermo_id", dermo_id), limit=1, with_payload=["disease_id"])
        if not records or not records[0].payload:
            return None
        return records[0].payload.get("disease_id")

    async def get_kb_chunks_by_disease_id(self, disease_id: str) -> list[Record]:
        """Lấy TOÀN BỘ chunk (tối đa 5: overview/symptoms/differential/advice/risk) của ĐÚNG 1 bệnh theo `disease_id` — filter thuần trên
        payload, KHÔNG cần vector (khác `search_kb_chunks`, vốn semantic search theo câu hỏi tự do). Dùng khi đã biết chính xác bệnh cần
        đào sâu, tránh gọi lại semantic search nhiều lần."""
        return await self._qdrant.scroll(settings.QDRANT_KB_COLLECTION, eq_filter("disease_id", disease_id), limit=5)

    # ----- phenotype PrimeKG -----
    async def ensure_phenotype_collection(self, dim: int) -> None:
        await self._qdrant.ensure_collection(settings.QDRANT_PHENOTYPE_COLLECTION, dim)

    async def delete_phenotype_collection(self) -> None:
        await self._qdrant.delete_collection(settings.QDRANT_PHENOTYPE_COLLECTION)

    async def upsert_phenotypes(self, points: list[PointStruct]) -> None:
        await self._qdrant.upsert_points(settings.QDRANT_PHENOTYPE_COLLECTION, points)

    async def search_phenotypes(self, *, vector: list[float], limit: int = 5) -> list[ScoredPoint]:
        return await self._qdrant.search(settings.QDRANT_PHENOTYPE_COLLECTION, vector, limit=limit)
