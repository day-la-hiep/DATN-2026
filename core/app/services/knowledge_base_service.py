"""Truy cập Qdrant cho chunk sách (`settings.QDRANT_DOCUMENT_COLLECTION` do pipeline `document_ingest` nạp, cộng collection cũ
`settings.QDRANT_LEGACY_BOOK_COLLECTION` nếu còn): tên collection và truy vấn đặc thù cho agent, xây trên capability generic của
`QdrantVectorClient` (`app/infra/qdrant_client.py`); instance do `app/api/deps.py` tạo. Phía ghi (index, xoá chunk) do
`DocumentService` đảm nhiệm; ở đây chỉ có phía đọc, dùng bởi `agent/tools/hybrid_retrieval/`."""
from typing import Any

from qdrant_client.models import Record, ScoredPoint

from app.config.settings import settings
from app.infra.qdrant_client import QdrantVectorClient


def _normalize_legacy(payload: dict[str, Any] | None) -> None:
    """Payload collection cũ dùng `book_id`/`book_title`; đưa về tên `document_*` để tool trích dẫn nguồn đúng."""
    if payload:
        payload.setdefault("document_id", payload.get("book_id"))
        payload.setdefault("document_title", payload.get("book_title"))


class KnowledgeBaseService:
    def __init__(self, qdrant: QdrantVectorClient) -> None:
        self._qdrant = qdrant

    def _collections(self) -> list[str]:
        legacy = settings.QDRANT_LEGACY_BOOK_COLLECTION
        return [settings.QDRANT_DOCUMENT_COLLECTION, *([legacy] if legacy else [])]

    def _fix(self, name: str, payload: dict[str, Any] | None) -> None:
        if name == settings.QDRANT_LEGACY_BOOK_COLLECTION:
            _normalize_legacy(payload)

    async def search_document_chunks(self, *, vector: list[float], limit: int) -> list[ScoredPoint]:
        """Semantic search trên chunk sách ở mọi collection; chưa có collection nào (chưa index sách) -> rỗng. Cùng một embedding
        model nên điểm cosine so sánh được, gộp theo điểm giảm dần."""
        points: list[ScoredPoint] = []
        for name in self._collections():
            if not await self._qdrant.collection_exists(name):
                continue
            found = await self._qdrant.search(name, vector, limit=limit)
            for p in found:
                self._fix(name, p.payload)
            points += found
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]

    async def count_document_chunks(self) -> int:
        return sum([await self._qdrant.count(name) for name in self._collections()])

    async def all_document_chunks(self) -> list[Record]:
        """Mọi chunk sách kèm payload, để dựng chỉ mục BM25 (`agent/tools/hybrid_retrieval/bm25.py`)."""
        records: list[Record] = []
        for name in self._collections():
            found = await self._qdrant.scroll_all(name)
            for r in found:
                self._fix(name, r.payload)
            records += found
        return records
