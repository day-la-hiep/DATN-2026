"""Nhánh từ khoá của `hybrid_retrieval`: BM25 do Qdrant chấm trên sparse vector `bm25` của chunk sách (bước `index` của pipeline
nạp cùng lúc với dense vector), nên không dựng chỉ mục trong RAM — nạp / xoá sách có hiệu lực ngay, không cần khởi động lại worker."""
from typing import Any

from app.api.deps import get_knowledge_base_service


async def bm25_search(query: str, limit: int) -> list[dict[str, Any]]:
    """Payload các chunk khớp từ khoá nhất, theo thứ tự giảm dần; rỗng khi chưa index sách nào (hoặc không từ nào trùng)."""
    points = await get_knowledge_base_service().search_document_chunks_bm25(query=query, limit=limit)
    return [p.payload for p in points if p.payload]
