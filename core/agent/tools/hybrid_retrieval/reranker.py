"""Rerank bằng cross-encoder local (sentence-transformers `CrossEncoder`, không gọi API ngoài), bước cuối của `hybrid_retrieval`.

Model đa ngôn ngữ để chấm được cả tiếng Việt lẫn câu KG tiếng Anh (`settings.RERANKER_MODEL`). Tải model lười ở lần dùng đầu
tiên; không tải / chạy được thì `rerank` trả `None` để caller giữ thứ tự cũ thay vì làm hỏng cả lượt tìm kiếm."""
import asyncio
import math

from sentence_transformers import CrossEncoder

from app.config.settings import settings

_model: CrossEncoder | None = None
_failed = False


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder(settings.RERANKER_MODEL)
    return _model


def _score(query: str, passages: list[str]) -> list[float]:
    logits = _get_model().predict([(query, p) for p in passages])
    return [1.0 / (1.0 + math.exp(-float(x))) for x in logits]  # logit -> 0..1 để dễ đọc trong kết quả


async def rerank(query: str, passages: list[str]) -> list[float] | None:
    """Điểm liên quan 0..1 cho từng đoạn, cùng thứ tự `passages`; `None` nếu cross-encoder không dùng được."""
    global _failed
    if not passages or _failed:
        return None if _failed else []
    try:
        return await asyncio.to_thread(_score, query, passages)
    except Exception as exc:  # noqa: BLE001  # thiếu mạng lần đầu tải model, thiếu RAM...
        _failed = True  # không thử lại mỗi lượt: tải model hỏng thường kéo dài cả phiên chạy
        print(f"[Reranker] không dùng được {settings.RERANKER_MODEL}: {exc}")
        return None
