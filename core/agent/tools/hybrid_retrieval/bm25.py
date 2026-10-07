"""Chỉ mục BM25 trong bộ nhớ trên chunk sách (Qdrant `QDRANT_DOCUMENT_COLLECTION`), nhánh từ khoá của `hybrid_retrieval`.

Dựng từ toàn bộ payload của collection (chỉ hợp lý với kho cỡ vài nghìn chunk — đồ án), lười ở lần tìm đầu tiên và dựng lại
khi số chunk trong Qdrant đổi (có sách mới được index / bị xoá). Chỉ đếm số point nên nếu nạp lại sách với cùng số chunk thì
chỉ mục có thể cũ cho tới khi worker khởi động lại — chấp nhận được ở quy mô này."""
import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from app.api.deps import get_knowledge_base_service

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Chữ thường, tách theo từ (âm tiết với tiếng Việt). Giữ dấu: bỏ dấu sẽ gộp các từ khác nghĩa ("ma" / "má" / "mạ")."""
    return _TOKEN_RE.findall(unicodedata.normalize("NFC", text).lower())


@dataclass
class Bm25Hit:
    payload: dict[str, Any]
    score: float


class Bm25Index:
    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._payloads: list[dict[str, Any]] = []
        self._count = -1
        self._lock = asyncio.Lock()

    async def _ensure_fresh(self) -> None:
        kb = get_knowledge_base_service()
        count = await kb.count_document_chunks()
        if count == self._count:
            return
        async with self._lock:
            if count == self._count:
                return
            records = await kb.all_document_chunks()
            payloads = [r.payload for r in records if r.payload and r.payload.get("text")]
            # tokenize + dựng BM25 là CPU thuần, đẩy ra thread để không chặn event loop của worker
            self._bm25 = (
                await asyncio.to_thread(lambda: BM25Okapi([tokenize(_index_text(p)) for p in payloads])) if payloads else None
            )
            self._payloads, self._count = payloads, count

    async def search(self, query: str, limit: int) -> list[Bm25Hit]:
        await self._ensure_fresh()
        tokens = tokenize(query)
        if self._bm25 is None or not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:limit]
        return [Bm25Hit(self._payloads[i], float(scores[i])) for i in order if scores[i] > 0]


def _index_text(payload: dict[str, Any]) -> str:
    # `context_text` = đường dẫn mục lục + nội dung, nên từ khoá trong tên chương / mục cũng khớp được
    return str(payload.get("context_text") or payload.get("text") or "")


_index = Bm25Index()


def get_bm25_index() -> Bm25Index:
    return _index
