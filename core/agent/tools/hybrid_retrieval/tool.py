"""Tool tra cứu cho agent"""
import asyncio
import json
from typing import Any, TypeVar

from langchain_core.tools import tool

from agent.tools.hybrid_retrieval.bm25 import bm25_search
from agent.tools.hybrid_retrieval.fusion import book_result, fallback_top, merge_chunks
from agent.tools.hybrid_retrieval.kg import kg_search
from agent.tools.hybrid_retrieval.reranker import rerank
from agent.tools.hybrid_retrieval.semantic import semantic_search as semantic_leg

T = TypeVar("T")

_LEG_LIMIT = 20  # số chunk lấy về từ mỗi nhánh (semantic / BM25) trước khi trộn / rerank
_POOL = 20  # số chunk giữ lại sau RRF để đem rerank (hybrid_retrieval)
_PASSAGE_CHARS = 1200  # cắt đoạn đưa vào cross-encoder (model nhỏ, ngữ cảnh ngắn)
_MAX_TOP_K = 10


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _clean(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"rank": i, **{k: v for k, v in r.items() if not k.startswith("_") and v != ""}} for i, r in enumerate(results, start=1)]


async def _book_response(query: str, payloads: list[dict[str, Any]], top_k: int, leg: str, empty_note: str) -> str:
    """Rerank các đoạn sách của một nhánh theo câu hỏi; không rerank được thì giữ thứ tự của nhánh đó."""
    notes: list[str] = []
    if not payloads:
        return _dump({"query": query, "evidence_found": False, "results": [], "notes": [empty_note]})
    candidates = [
        {**book_result(p), "_passage": str(p.get("context_text") or p.get("text", ""))[:_PASSAGE_CHARS]} for p in payloads
    ]
    scores = await rerank(query, [c["_passage"] for c in candidates])
    if scores is not None:
        for c, s in zip(candidates, scores, strict=True):
            c["score"] = round(s, 3)
        candidates.sort(key=lambda c: c["score"], reverse=True)
        ranked_by = "reranker"
    else:
        notes.append(f"Không rerank được (cross-encoder không khả dụng) — giữ thứ tự của nhánh {leg}.")
        ranked_by = leg
    return _dump(
        {"query": query, "evidence_found": True, "ranked_by": ranked_by, "results": _clean(candidates[:top_k]), "notes": notes}
    )


def _unwrap(name: str, result: list[T] | BaseException, notes: list[str]) -> list[T]:
    """Nhánh lỗi -> rỗng + ghi chú, để các nhánh còn lại vẫn cho kết quả."""
    if isinstance(result, BaseException):
        notes.append(f"Nhánh {name} không dùng được: {type(result).__name__}: {result}")
        return []
    return result


async def _bm25_payloads(query: str) -> list[dict[str, Any]]:
    return await bm25_search(query, _LEG_LIMIT)


@tool
async def hybrid_retrieval(query: str, top_k: int = 5) -> str:
    """Tra cứu tri thức da liễu từ SÁCH GIÁO KHOA đã số hoá và đồ thị tri thức (PrimeKG/DermO) trong MỘT lần gọi: tìm theo
    ngữ nghĩa + từ khoá + đồ thị rồi xếp hạng lại theo độ liên quan tới câu hỏi. Là tool MẶC ĐỊNH cho yêu cầu chung chung hoặc
    chưa rõ cần loại thông tin nào (mô tả bệnh, triệu chứng, phân biệt chẩn đoán, điều trị, chống chỉ định, yếu tố nguy cơ) —
    kèm nguồn trích dẫn. Khi đã lập luận rõ cần đúng thông tin gì (vd khớp chính xác tên thuốc, hay chỉ cần quan hệ đồ thị) thì
    cân nhắc `semantic_search` / `keyword_search` / `knowledge_graph_search` để lấy đúng thứ cần.

    Mỗi kết quả có `source`: "book" (đoạn sách, kèm `title`, `section`, `pages` để trích dẫn) hoặc "kg" (một quan hệ / bệnh
    ứng viên từ đồ thị tri thức, chưa phải kết luận). `score` là độ liên quan 0..1 sau rerank (không phải xác suất chẩn
    đoán); `ranked_by` cho biết có rerank được hay chỉ dùng thứ tự trộn. Phần `notes` nêu nhánh nào không dùng được — khi đó
    nói rõ là chưa tra được nguồn đó thay vì suy đoán.

    Args:
        query: Câu hỏi hoặc mô tả cần tra, tiếng Việt hoặc Anh, nêu rõ bệnh / triệu chứng / thuốc. Mỗi lần gọi một chủ đề cụ
            thể sẽ cho kết quả tốt hơn một câu dài trộn nhiều ý.
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    semantic_r, bm25_r, kg_r = await asyncio.gather(
        semantic_leg(query, _LEG_LIMIT), _bm25_payloads(query), kg_search(query), return_exceptions=True
    )
    notes: list[str] = []
    semantic = _unwrap("semantic", semantic_r, notes)
    bm25 = _unwrap("bm25", bm25_r, notes)
    kg = _unwrap("kg", kg_r, notes)

    # trộn 2 nhánh chunk theo RRF, khử trùng theo chunk_id
    chunks = merge_chunks(semantic, bm25, _POOL)
    candidates: list[dict[str, Any]] = [
        {**book_result(p), "_passage": str(p.get("context_text") or p.get("text", ""))[:_PASSAGE_CHARS]} for p in chunks
    ]
    candidates += [{"source": "kg", "title": "PrimeKG / DermO", "text": fact, "_passage": fact} for fact in kg]
    if not candidates:
        return _dump(
            {
                "query": query,
                "evidence_found": False,
                "results": [],
                "notes": [*notes, "KHÔNG có bằng chứng: không có đoạn sách nào khớp (chưa index sách, hoặc không có đoạn liên quan) và đồ thị không có dữ liệu."],
            }
        )

    scores = await rerank(query, [c["_passage"] for c in candidates])
    if scores is not None:
        for c, s in zip(candidates, scores, strict=True):
            c["score"] = round(s, 3)
        ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:top_k]
        ranked_by = "reranker"
    else:
        notes.append("Không rerank được (cross-encoder không khả dụng) — dùng thứ tự trộn semantic + BM25.")
        ranked = fallback_top(candidates, top_k)
        ranked_by = "rrf"

    results = _clean(ranked)
    evidence_found = any(r["source"] == "book" for r in results)
    if not evidence_found:
        notes.append("Chỉ có gợi ý từ đồ thị tri thức, KHÔNG có đoạn sách nào làm bằng chứng — không khẳng định bệnh dựa vào đó.")
    return _dump({"query": query, "evidence_found": evidence_found, "ranked_by": ranked_by, "results": results, "notes": notes})


@tool
async def semantic_search(query: str, top_k: int = 5) -> str:
    """Tìm đoạn SÁCH GIÁO KHOA da liễu đã số hoá theo NGỮ NGHĨA (embedding) — hợp với câu hỏi diễn đạt tự nhiên, mô tả triệu
    chứng, khái niệm; bắt được cả khi sách dùng từ khác với câu hỏi. Dùng để lấy bằng chứng (mô tả bệnh, triệu chứng, phân biệt
    chẩn đoán, điều trị, chống chỉ định, yếu tố nguy cơ) kèm nguồn trích dẫn. Cần khớp đúng tên thuốc / mã / thuật ngữ → dùng
    `keyword_search`. Tool chuyên biệt: dùng khi đã rõ cần tra theo ngữ nghĩa; yêu cầu chung chung → `hybrid_retrieval`.

    Mỗi kết quả có `source="book"` kèm `title`, `section`, `pages` để trích dẫn; `score` là độ liên quan 0..1 sau rerank (không
    phải xác suất chẩn đoán). `evidence_found=false` hoặc `notes` báo lỗi → nói rõ là chưa tra được nguồn này thay vì suy đoán.

    Args:
        query: Câu hỏi hoặc mô tả cần tra, tiếng Việt hoặc Anh, nêu rõ bệnh / triệu chứng / thuốc. Mỗi lần một chủ đề cụ thể.
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    try:
        payloads = await semantic_leg(query, _LEG_LIMIT)
    except Exception as exc:  # noqa: BLE001  # Qdrant / embedding lỗi -> báo cho model thay vì làm hỏng cả lượt
        return _dump({"query": query, "evidence_found": False, "results": [], "notes": [f"semantic_search không dùng được: {type(exc).__name__}: {exc}"]})
    return await _book_response(
        query, payloads, top_k, "semantic", "KHÔNG có đoạn sách nào khớp (chưa index sách, hoặc không có đoạn liên quan)."
    )


@tool
async def keyword_search(query: str, top_k: int = 5) -> str:
    """Tìm đoạn SÁCH GIÁO KHOA da liễu đã số hoá theo TỪ KHOÁ (BM25) — hợp khi cần khớp đúng tên thuốc, hoạt chất, mã, tên bệnh
    hay thuật ngữ chuyên môn mà tìm theo ngữ nghĩa hay bỏ lỡ. Query nên là vài từ khoá chính (tên bệnh / thuốc / thuật ngữ), không
    phải câu dài. Câu hỏi diễn đạt tự nhiên, mô tả triệu chứng → dùng `semantic_search`.

    Kết quả cùng dạng với `semantic_search`: `source="book"` kèm `title`, `section`, `pages`; `score` là độ liên quan 0..1 sau
    rerank. `evidence_found=false` → không đoạn nào chứa từ khoá đó.

    Args:
        query: Các từ khoá cần khớp, tiếng Việt hoặc Anh (vd "methotrexate chống chỉ định", "vảy nến mảng").
        top_k: Số kết quả trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    try:
        payloads = await _bm25_payloads(query)
    except Exception as exc:  # noqa: BLE001
        return _dump({"query": query, "evidence_found": False, "results": [], "notes": [f"keyword_search không dùng được: {type(exc).__name__}: {exc}"]})
    return await _book_response(
        query, payloads, top_k, "bm25", "KHÔNG có đoạn sách nào chứa các từ khoá này (chưa index sách, hoặc không khớp)."
    )


@tool
async def knowledge_graph_search(query: str, top_k: int = 8) -> str:
    """Tra ĐỒ THỊ TRI THỨC PrimeKG / DermO: quan hệ bệnh–triệu chứng–thuốc (chỉ định, chống chỉ định) và BỆNH ỨNG VIÊN có cùng
    triệu chứng. Hợp để gợi ý hướng khi mô tả chỉ có triệu chứng, hoặc để lấy quan hệ thuốc–bệnh. Kết quả CHỈ LÀ GỢI Ý
    (`source="kg"`, điểm đồ thị là heuristic), KHÔNG phải bằng chứng lâm sàng và không phải chẩn đoán: muốn khẳng định phải đối
    chiếu bằng `semantic_search` / `keyword_search`.

    Tool tự trích thực thể y khoa từ câu hỏi (dịch sang tiếng Anh), nên nêu rõ tên bệnh / triệu chứng / thuốc. `notes` báo lỗi
    (Neo4j chưa chạy...) → nói rõ là chưa tra được đồ thị.

    Args:
        query: Câu hỏi hoặc mô tả có tên bệnh / triệu chứng / thuốc, tiếng Việt hoặc Anh.
        top_k: Số quan hệ / bệnh ứng viên trả về (1-10, mặc định 8).
    """
    top_k = min(max(top_k, 1), _MAX_TOP_K)
    try:
        facts = await kg_search(query, limit=top_k)
    except Exception as exc:  # noqa: BLE001
        return _dump({"query": query, "results": [], "notes": [f"knowledge_graph_search không dùng được: {type(exc).__name__}: {exc}"]})
    notes = [] if facts else ["Đồ thị không có dữ liệu cho câu hỏi này (không trích được thực thể hoặc đồ thị không có quan hệ)."]
    results = _clean([{"source": "kg", "title": "PrimeKG / DermO", "text": fact} for fact in facts])
    return _dump({"query": query, "results": results, "notes": notes})
