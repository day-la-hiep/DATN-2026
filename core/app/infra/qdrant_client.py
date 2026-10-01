"""Qdrant dùng chung: class `QdrantVectorClient` = kết nối (async cho Core/Agent, đồng bộ cho pipeline chạy ở thread nền) + capability generic
(đảm bảo/xoá collection, upsert, search, retrieve, scroll, lọc theo payload). Tên collection và payload cụ thể của từng loại dữ liệu
nằm ở service (`KnowledgeBaseService`, `BookService`). Instance do `app/api/deps.py` tạo và đóng."""
import threading
from typing import Any

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Record,
    ScoredPoint,
    VectorParams,
)

from app.config.settings import settings


def eq_filter(key: str, value: Any) -> Filter:
    """Bộ lọc payload `key == value`."""
    return Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))])


class QdrantVectorClient:
    def __init__(self, url: str, api_key: str | None = None, *, sync_client: QdrantClient | None = None) -> None:
        """`sync_client` cho phép thay client đồng bộ (test dùng `QdrantClient(":memory:")`)."""
        self._url, self._api_key = url, api_key or None
        self._async: AsyncQdrantClient | None = None
        self._sync = sync_client
        self._guard = threading.Lock()

    @classmethod
    def from_settings(cls) -> "QdrantVectorClient":
        return cls(settings.QDRANT_URL, settings.QDRANT_API_KEY or None)

    @property
    def client(self) -> AsyncQdrantClient:
        with self._guard:
            if self._async is None:
                self._async = AsyncQdrantClient(url=self._url, api_key=self._api_key)
            return self._async

    @property
    def sync_client(self) -> QdrantClient:
        with self._guard:
            if self._sync is None:
                self._sync = QdrantClient(url=self._url, api_key=self._api_key)
            return self._sync

    async def close(self) -> None:
        if self._async is not None:
            await self._async.close()
            self._async = None
        if self._sync is not None:
            self._sync.close()
            self._sync = None

    # ---------------------------------------------------------------- async (Core / Agent)
    async def ensure_collection(self, name: str, dim: int) -> None:
        """Tạo collection cosine nếu chưa có (idempotent)."""
        if not await self.client.collection_exists(name):
            await self.client.create_collection(name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    async def delete_collection(self, name: str) -> None:
        """Xoá collection (no-op khi chưa tồn tại)."""
        if await self.client.collection_exists(name):
            await self.client.delete_collection(name)

    async def upsert_points(self, name: str, points: list[PointStruct]) -> None:
        await self.client.upsert(name, points=points)

    async def search(self, name: str, vector: list[float], *, limit: int, query_filter: Filter | None = None,
                     score_threshold: float | None = None) -> list[ScoredPoint]:
        result = await self.client.query_points(name, query=vector, query_filter=query_filter, limit=limit,
                                                score_threshold=score_threshold)
        return result.points

    async def existing_ids(self, name: str, ids: list[str]) -> set[str]:
        """Trong `ids`, những id đã có trong collection (không tải payload/vector)."""
        if not ids:
            return set()
        records = await self.client.retrieve(name, ids=ids, with_payload=False, with_vectors=False)
        return {str(r.id) for r in records}

    async def scroll(self, name: str, query_filter: Filter, *, limit: int, with_payload: bool | list[str] = True) -> list[Record]:
        """Lấy point theo bộ lọc payload thuần (không cần vector)."""
        records, _ = await self.client.scroll(name, scroll_filter=query_filter, limit=limit, with_payload=with_payload)
        return records

    # ---------------------------------------------------------------- đồng bộ (pipeline ở thread nền)
    def ensure_collection_sync(self, name: str, dim: int, *, keyword_index_fields: tuple[str, ...] = ()) -> None:
        """Tạo collection nếu chưa có; có rồi thì kiểm tra số chiều khớp. Tạo chỉ mục keyword cho các trường lọc/xoá nhiều."""
        client = self.sync_client
        if not client.collection_exists(name):
            client.create_collection(name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
        else:
            size = client.get_collection(name).config.params.vectors.size  # type: ignore[union-attr]
            if size != dim:
                raise RuntimeError(f"Collection {name} có vector {size} chiều, khác embedding hiện tại ({dim} chiều).")
        for field in keyword_index_fields:
            try:
                client.create_payload_index(name, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
            except Exception:  # noqa: BLE001  # chỉ mục đã có / local mode không hỗ trợ
                pass

    def delete_by_filter_sync(self, name: str, query_filter: Filter) -> None:
        client = self.sync_client
        if client.collection_exists(name):
            client.delete(name, points_selector=FilterSelector(filter=query_filter), wait=True)

    def count_sync(self, name: str, query_filter: Filter | None = None) -> int:
        client = self.sync_client
        if not client.collection_exists(name):
            return 0
        return int(client.count(name, count_filter=query_filter, exact=True).count)

    def upsert_points_sync(self, name: str, points: list[PointStruct]) -> None:
        self.sync_client.upsert(name, points=points, wait=True)
