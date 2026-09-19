"""Tool tra cứu guideline da liễu dạng văn bản — dữ liệu 435 chunk trích từ 87 bệnh
(BYT 75/QĐ-BYT 2015, WHO Fact Sheets, MedlinePlus), xem `knowledge_base/README.md` cho
pipeline chunking gốc (`knowledge_base/scripts/build_chunks_kb2.py`,
`knowledge_base/data/chunks/all_chunks.json`). Chunk được embed + ingest MỘT LẦN vào
Qdrant qua `scripts/ingest/ingest_knowledge_base.py` (không đọc file JSON lúc runtime —
cùng nguyên tắc "ingest riêng, tool chỉ query store" như `knowledge_graph.py`/
`dermo_terms.py` dùng Neo4j).

Khác `query_dermatology_kg` (`knowledge_graph.py`, quan hệ CÓ CẤU TRÚC bệnh-triệu
chứng/thuốc từ PrimeKG, LLM tự sinh Cypher): tool này trả ĐOẠN VĂN BẢN GỐC trích từ
guideline lâm sàng kèm trích dẫn nguồn (source_label/source_page) — dùng khi cần mô tả
triệu chứng, phân biệt chẩn đoán, lời khuyên chăm sóc hoặc yếu tố nguy cơ dạng tự nhiên,
có thể trích dẫn/diễn giải trực tiếp cho người dùng thay vì suy luận từ quan hệ graph.

2 tool trong file này phối hợp theo 2 bước — tìm rộng rồi đào sâu ĐÚNG 1 bệnh:
  - `search_disease_guidelines`: semantic search tự do, top-k có thể trải trên NHIỀU
    bệnh khác nhau (mỗi kết quả tự mang `chunk_type` khớp điểm cao nhất).
  - `get_disease_guideline_profile`: 1 khi đã có `disease_id` cụ thể (từ kết quả tool
    trên), lấy ĐỦ cả 5 khía cạnh (overview/symptoms/differential/advice/risk) của
    ĐÚNG bệnh đó trong 1 lần gọi — filter theo payload, không phải semantic search, nên
    không có rủi ro lần gọi sau trúng nhầm bệnh khác.

Embedding: LOCAL (`app/agent/embeddings.py`, sentence-transformers — KHÔNG cần API
key, cùng embedding dùng bởi long-term memory `app/agent/memory.py`), 384 chiều —
PHẢI khớp `KB_EMBEDDING_DIM` dùng khi ingest (`scripts/ingest/ingest_knowledge_base.py`)
và `ensure_kb_collection(dim=...)` (`app/infra/qdrant_client.py`). Collection Qdrant
riêng (`settings.QDRANT_KB_COLLECTION`), KHÔNG lẫn với collection memory người dùng.
"""

from typing import Any

from langchain_core.tools import tool
from qdrant_client.models import Record, ScoredPoint

from app.agent.embeddings import EMBEDDING_DIM, LocalEmbeddings
from app.infra.qdrant_client import get_kb_chunks_by_disease_id, search_kb_chunks

KB_EMBEDDING_DIM = EMBEDDING_DIM

# Thứ tự hiển thị cố định — `get_kb_chunks_by_disease_id` dùng `scroll()` (filter thuần,
# không phải semantic search) nên Qdrant KHÔNG đảm bảo thứ tự trả về giống thứ tự ingest.
_CHUNK_TYPE_ORDER = ["overview", "symptoms", "differential", "risk", "advice"]

_embeddings: LocalEmbeddings | None = None


def get_kb_embeddings() -> LocalEmbeddings:
    """Dùng chung bởi tool này (embed query) và `scripts/ingest/ingest_knowledge_base.py`
    (embed toàn bộ chunk) — đảm bảo luôn cùng model/dim."""
    global _embeddings
    if _embeddings is None:
        _embeddings = LocalEmbeddings()
    return _embeddings


def _format_source(payload: dict[str, Any]) -> str:
    source = str(payload.get("source_label", ""))
    if payload.get("source_page"):
        source += f" tr.{payload['source_page']}"
    return source or "không rõ"


def _format_match(point: ScoredPoint) -> str:
    payload = point.payload or {}
    return (
        f"{payload.get('disease_name', '?')} ({payload.get('chunk_type', '?')}) "
        f"— độ liên quan: {point.score:.2f}\n"
        f"{payload.get('text', '')}\n"
        f"Nguồn: {_format_source(payload)}"
    )


def _format_record(record: Record) -> str:
    payload = record.payload or {}
    return (
        f"[{payload.get('chunk_type', '?')}] {payload.get('text', '')}\n"
        f"Nguồn: {_format_source(payload)}"
    )


@tool
async def search_disease_guidelines(query: str, chunk_type: str = "all", top_k: int = 3) -> str:
    """Tìm đoạn văn bản guideline da liễu (BYT 2015/WHO/MedlinePlus) liên quan tới câu
    hỏi hoặc mô tả triệu chứng của người dùng — trả về text gốc kèm trích dẫn nguồn để
    làm CLINICAL_EVIDENCE. Gọi tool này khi người dùng mô tả triệu chứng, hỏi về một
    bệnh da liễu cụ thể, hỏi cách phân biệt hai bệnh, hỏi lời khuyên chăm sóc, hoặc hỏi
    yếu tố nguy cơ/dấu hiệu cảnh báo.

    Args:
        query: Câu hỏi hoặc mô tả triệu chứng của người dùng, giữ nguyên ngôn ngữ gốc.
        chunk_type: Loại thông tin cần tìm — "overview" (định nghĩa/mô tả chung bệnh),
            "symptoms" (triệu chứng, dấu hiệu lâm sàng, vị trí tổn thương),
            "differential" (phân biệt chẩn đoán giữa các bệnh), "advice" (lời khuyên
            chăm sóc/khi nào cần khám), "risk" (yếu tố nguy cơ, dấu hiệu cảnh báo nguy
            hiểm), hoặc "all" (mặc định — tìm trong mọi loại chunk).
        top_k: Số kết quả tối đa trả về (1-10, mặc định 3).
    """
    top_k = min(max(top_k, 1), 10)
    vector = await get_kb_embeddings().aembed_query(query)
    matches = await search_kb_chunks(vector=vector, limit=top_k, chunk_type=chunk_type)

    if not matches:
        return "Không tìm thấy đoạn guideline nào phù hợp trong cơ sở dữ liệu."

    return "\n\n".join(_format_match(match) for match in matches)


@tool
async def get_disease_guideline_profile(disease_id: str) -> str:
    """Lấy ĐẦY ĐỦ hồ sơ guideline (overview, symptoms, differential, advice, risk — tối
    đa 5 mục) của ĐÚNG 1 bệnh theo `disease_id`. Dùng SAU KHI đã xác định bệnh cần đào
    sâu — ví dụ lấy `disease_id` từ 1 kết quả của `search_disease_guidelines` — thay vì
    gọi lại `search_disease_guidelines` nhiều lần với `chunk_type` khác nhau (không đảm
    bảo mỗi lần đều trúng cùng 1 bệnh vì đó là semantic search tự do).

    Args:
        disease_id: Id bệnh lấy từ payload kết quả `search_disease_guidelines` (field
            `disease_id`, vd "mun_trung_ca_medlineplus"), KHÔNG phải tên bệnh tự do.
    """
    records = await get_kb_chunks_by_disease_id(disease_id)

    if not records:
        return f"Không tìm thấy bệnh nào với disease_id='{disease_id}' trong cơ sở dữ liệu."

    ordered = sorted(
        records,
        key=lambda r: _CHUNK_TYPE_ORDER.index((r.payload or {}).get("chunk_type", ""))
        if (r.payload or {}).get("chunk_type") in _CHUNK_TYPE_ORDER
        else len(_CHUNK_TYPE_ORDER),
    )
    disease_name = (ordered[0].payload or {}).get("disease_name", disease_id)
    header = f"Hồ sơ guideline: {disease_name} ({disease_id})"
    return header + "\n\n" + "\n\n".join(_format_record(r) for r in ordered)
