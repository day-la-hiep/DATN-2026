"""Truy cập Qdrant cho chunk sách"""
from typing import Any

from qdrant_client.models import Record, ScoredPoint

from app.config.settings import settings
import asyncio

from app.infra.bm25 import LANGUAGES, SPARSE_NAME, encode_query
from app.infra.qdrant_client import QdrantVectorClient, eq_filter


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
        """Semantic search trên chunk sách ở mọi collection"""
        points: list[ScoredPoint] = []
        for name in self._collections():
            # collection cũ (vd 384 chiều) không so được với embedding hiện tại; query vào sẽ 400 làm hỏng cả nhánh semantic
            if await self._qdrant.dense_size(name) != len(vector):
                continue
            found = await self._qdrant.search(name, vector, limit=limit)
            for p in found:
                self._fix(name, p.payload)
            points += found
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]

    async def search_document_chunks_bm25(self, *, query: str, limit: int) -> list[ScoredPoint]:
        """Tìm từ khoá: mỗi nhóm đoạn (theo `bm25_mode`) được tìm bằng câu hỏi mã hoá đúng cách của nhóm đó"""
        points: list[ScoredPoint] = []
        for name in self._collections():
            if not await self._qdrant.has_sparse_vector(name, SPARSE_NAME):
                continue
            found = await asyncio.gather(
                *(self._qdrant.search_sparse(name, encode_query(query, mode), using=SPARSE_NAME, limit=limit,
                                             query_filter=eq_filter("bm25_mode", mode)) for mode in LANGUAGES)
            )
            for p in (p for group in found for p in group):
                self._fix(name, p.payload)
                points.append(p)
        return sorted(points, key=lambda p: p.score, reverse=True)[:limit]

    async def all_document_chunks(self) -> list[Record]:
        """Mọi chunk sách kèm payload, chỉ để thống kê / kiểm tra bằng tay (`agent/test/`); tìm kiếm không đọc cả kho."""
        records: list[Record] = []
        for name in self._collections():
            found = await self._qdrant.scroll_all(name)
            for r in found:
                self._fix(name, r.payload)
            records += found
        return records
