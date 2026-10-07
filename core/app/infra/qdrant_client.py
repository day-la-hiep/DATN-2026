"""Qdrant dùng chung: class `QdrantVectorClient` = kết nối (async cho Core/Agent, đồng bộ cho pipeline chạy ở thread nền) + capability generic
(đảm bảo/xoá collection, upsert, search dense + sparse, lọc theo payload). Tên collection và payload cụ thể của từng loại dữ liệu
nằm ở service (`KnowledgeBaseService`, `DocumentService`). Instance do `app/api/deps.py` tạo và đóng."""
import threading
from typing import Any

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    Record,
    ScoredPoint,
    SparseVector,
    SparseVectorParams,
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
    async def search(self, name: str, vector: list[float], *, limit: int, query_filter: Filter | None = None,
                     score_threshold: float | None = None) -> list[ScoredPoint]:
        result = await self.client.query_points(name, query=vector, query_filter=query_filter, limit=limit,
                                                score_threshold=score_threshold)
        return result.points

    async def search_sparse(self, name: str, vector: SparseVector, *, using: str, limit: int,
                            query_filter: Filter | None = None) -> list[ScoredPoint]:
        """Tìm theo sparse vector đã đặt tên (BM25); chỉ trả point có điểm > 0, tức có ít nhất một từ trùng."""
        if not vector.indices:
            return []
        result = await self.client.query_points(name, query=vector, using=using, query_filter=query_filter, limit=limit)
        return result.points

    async def has_sparse_vector(self, name: str, vector_name: str) -> bool:
        """Collection có sparse vector tên này không. Sparse vector chỉ khai báo được lúc tạo collection nên collection cũ
        (tạo trước khi có BM25 qua Qdrant) sẽ không có."""
        if not await self.client.collection_exists(name):
            return False
        sparse = (await self.client.get_collection(name)).config.params.sparse_vectors
        return bool(sparse) and vector_name in sparse

    async def collection_exists(self, name: str) -> bool:
        return await self.client.collection_exists(name)

    async def count(self, name: str) -> int:
        """Số point của collection; 0 khi collection chưa có."""
        if not await self.client.collection_exists(name):
            return 0
        return int((await self.client.count(name, exact=True)).count)

    async def scroll_all(self, name: str, *, with_payload: bool | list[str] = True, batch: int = 256) -> list[Record]:
        """Đọc toàn bộ point (không cần vector), phân trang. Chỉ dùng cho thống kê / kiểm tra bằng tay trên kho cỡ vài nghìn chunk."""
        if not await self.client.collection_exists(name):
            return []
        records: list[Record] = []
        offset = None
        while True:
            page, offset = await self.client.scroll(name, limit=batch, offset=offset, with_payload=with_payload)
            records += page
            if offset is None:
                return records

    # ---------------------------------------------------------------- đồng bộ (pipeline ở thread nền)
    def ensure_collection_sync(self, name: str, dim: int, *, keyword_index_fields: tuple[str, ...] = (),
                               sparse_names: tuple[str, ...] = ()) -> None:
        """Tạo collection nếu chưa có; có rồi thì kiểm tra số chiều và sparse vector khớp. Tạo chỉ mục keyword cho các trường
        lọc/xoá nhiều. `sparse_names` bật IDF phía Qdrant (cho BM25). Qdrant không cho thêm sparse vector vào collection đã
        tạo nên thiếu thì báo lỗi rõ thay vì nạp chunk không tìm được bằng từ khoá."""
        client = self.sync_client
        if not client.collection_exists(name):
            client.create_collection(
                name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                sparse_vectors_config={n: SparseVectorParams(modifier=Modifier.IDF) for n in sparse_names} or None,
            )
        else:
            params = client.get_collection(name).config.params
            size = params.vectors.size  # type: ignore[union-attr]
            if size != dim:
                raise RuntimeError(f"Collection {name} có vector {size} chiều, khác embedding hiện tại ({dim} chiều).")
            missing = [n for n in sparse_names if n not in (params.sparse_vectors or {})]
            if missing:
                raise RuntimeError(
                    f"Collection {name} thiếu sparse vector {', '.join(missing)} và Qdrant không thêm được vào collection đã tạo — "
                    "đặt QDRANT_DOCUMENT_COLLECTION sang tên mới rồi chạy lại bước Lưu vào kho tri thức."
                )
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
