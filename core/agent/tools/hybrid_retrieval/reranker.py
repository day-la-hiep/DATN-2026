"""Rerank bằng Qwen3-Reranker qua OpenRouter"""
import logging

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


async def rerank(query: str, passages: list[str]) -> list[float] | None:
    """Điểm liên quan 0..1 cho từng đoạn, cùng thứ tự `passages`; `None` nếu reranker không dùng được."""
    if not passages:
        return []
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.OPENROUTER_BASE_URL}/rerank",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json={"model": settings.RERANKER_MODEL, "query": query, "documents": passages},
            )
            resp.raise_for_status()
        scores = [0.0] * len(passages)
        for r in resp.json()["results"]:
            scores[r["index"]] = float(r["relevance_score"])
        return scores
    except Exception as exc:  # noqa: BLE001  # mất mạng, hết quota, model không có trên OpenRouter...
        logger.warning("không dùng được %s: %s", settings.RERANKER_MODEL, exc)
        return None
