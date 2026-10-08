"""Trộn kết quả các nhánh của `hybrid_retrieval`"""
from typing import Any

_RRF_K = 60  # hằng số chuẩn của RRF: giảm ảnh hưởng chênh lệch thứ hạng ở đầu danh sách
_KG_FALLBACK_SLOTS = 2  # khi không rerank được, vẫn dành chỗ cho câu KG trong top_k


def rrf(*rankings: list[str]) -> dict[str, float]:
    """Điểm RRF theo id"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    return scores


def merge_chunks(semantic: list[dict[str, Any]], bm25: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Payload chunk của hai nhánh, khử trùng theo `chunk_id`, xếp theo điểm RRF giảm dần, lấy `limit` đầu."""
    payloads: dict[str, dict[str, Any]] = {}
    for payload in [*semantic, *bm25]:
        payloads.setdefault(str(payload.get("chunk_id")), payload)
    scores = rrf([str(p.get("chunk_id")) for p in semantic], [str(p.get("chunk_id")) for p in bm25])
    return [payloads[k] for k in sorted(scores, key=lambda k: scores[k], reverse=True)[:limit]]


def _section(payload: dict[str, Any]) -> str:
    path = payload.get("toc_path")
    if isinstance(path, list):
        return " > ".join(str(p) for p in path if p)
    return str(path or "")


def _pages(payload: dict[str, Any]) -> str:
    # ưu tiên số trang in trên sách (người đọc đối chiếu được), không có thì dùng trang PDF
    start = payload.get("page_printed_start") or payload.get("page_start")
    end = payload.get("page_printed_end") or payload.get("page_end")
    if not start:
        return ""
    return f"tr.{start}" if not end or end == start else f"tr.{start}-{end}"


def book_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "book",
        "title": payload.get("document_title") or payload.get("document_id") or "?",
        "section": _section(payload),
        "pages": _pages(payload),
        "text": payload.get("text", ""),
    }


def fallback_top(candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Khi không rerank được: giữ thứ tự RRF của đoạn sách, nhưng dành vài chỗ cho câu KG để không bị loại hết khỏi top_k."""
    books = [c for c in candidates if c["source"] == "book"]
    facts = [c for c in candidates if c["source"] == "kg"]
    kg_slots = min(_KG_FALLBACK_SLOTS, len(facts), top_k // 2)
    return books[: top_k - kg_slots] + facts[:kg_slots]
