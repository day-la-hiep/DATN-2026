"""Tool pipeline: câu hỏi tự nhiên của người dùng -> trích xuất thực thể y khoa (JSON,
LLM structured output) -> chuẩn hoá từng thực thể qua DermO (`dermo_terms.py`, lấy từ
đồng nghĩa + định nghĩa) -> dùng chính các từ đồng nghĩa đó search PrimeKG
(`data/PrimeKG/load_to_neo4j.py`) lấy quan hệ lâm sàng (triệu chứng/thuốc/bệnh liên
quan) làm CONTEXT có cấu trúc cho model trả lời.

Khác 2 tool tra cứu đơn lẻ đã có:
  - `lookup_dermo_term` (`dermo_terms.py`): tra 1 thuật ngữ đã biết trước, trả text.
  - `query_dermatology_kg` (`knowledge_graph.py`): LLM tự sinh Cypher cho 1 câu hỏi mở.
Tool này gộp cả 3 bước (extract -> normalize -> search quan hệ) cho TOÀN BỘ câu hỏi
trong 1 lần gọi, trả JSON có cấu trúc — dùng khi câu hỏi có nhiều thực thể cùng lúc (vd
"da tôi đỏ, ngứa, đang dùng thuốc X") cần grounding đồng thời trước khi model suy luận.

QUAN TRỌNG — ràng buộc grounding: model KHÔNG được bổ sung fact y khoa từ kiến thức nền
riêng ngoài dữ liệu do tool trả về (`SYSTEM_PROMPT`, `graph.py`). Tool này (+
`query_dermatology_kg`, `lookup_dermo_term`) là nguồn quan hệ CÓ CẤU TRÚC (PrimeKG/DermO);
`search_disease_guidelines`/`get_disease_guideline_profile`
(`knowledge_base_search.py`) là nguồn văn bản guideline (BYT/WHO/MedlinePlus) — cả 2
nhóm đều là CLINICAL_EVIDENCE hợp lệ, KHÔNG còn là 2 tool duy nhất được phép như trước
khi có nhóm guideline. Thực thể extract được nhưng không tìm thấy trong DermO/PrimeKG
phải được nêu rõ là "không có dữ liệu trong phạm vi được cung cấp" (có thể vẫn tìm thấy
qua guideline text) chứ không suy đoán.
"""
import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel, Field

from app.agent.llm import get_model
from app.agent.tools.dermo_terms import search_dermo_terms
from app.core.config import settings

_EXTRACT_SYSTEM = (
    "Trích xuất các thực thể y khoa DA LIỄU (tên bệnh, triệu chứng, thuốc) được nhắc "
    "tới trong câu hỏi của người dùng. Dịch mỗi thực thể sang tên tiếng Anh y khoa chuẩn "
    "(dữ liệu tra cứu gốc là tiếng Anh, vd 'nổi mề đay' -> 'urticaria', 'da tôi đỏ và "
    "ngứa' -> 2 thực thể 'erythema' và 'pruritus'). CHỈ trích xuất thực thể RÕ RÀNG có "
    "trong câu hỏi — không suy đoán, không bổ sung thực thể không được nhắc tới. Nếu câu "
    "hỏi không chứa thực thể y khoa nào, trả về danh sách rỗng."
)

# Chỉ giữ quan hệ có giá trị lâm sàng (khớp `ALLOWED_RELATION_TYPES` của
# `data/PrimeKG/process_dermatology_kg.py`, viết hoa theo `to_rel_type` của
# `data/PrimeKG/load_to_neo4j.py`) — loại bỏ nhiễu mức phân tử/tế bào
# (protein-protein, anatomy-protein...) không cần cho grounding câu trả lời tư vấn.
_PRIMEKG_ALLOWED_RELS = [
    "DISEASE_PHENOTYPE_POSITIVE",
    "DISEASE_PHENOTYPE_NEGATIVE",
    "DISEASE_DISEASE",
    "INDICATION",
    "CONTRAINDICATION",
    "OFF_LABEL_USE",
]

_PRIMEKG_SEARCH_QUERY = """
MATCH (n:Entity)
WHERE any(name IN $names WHERE toLower(n.name) CONTAINS toLower(name))
WITH DISTINCT n
LIMIT $entity_limit
MATCH (n)-[r]-(m:Entity)
WHERE type(r) IN $allowed_rels
RETURN n.name AS entity, n.type AS entity_type, type(r) AS relation,
       m.name AS related, m.type AS related_type
LIMIT $rel_limit
"""

_primekg_driver: AsyncDriver | None = None


class ExtractedEntity(BaseModel):
    text: str = Field(
        description="Tên bệnh/triệu chứng/thuốc bằng tiếng Anh y khoa chuẩn, dịch từ "
        "câu hỏi gốc nếu cần"
    )
    type: Literal["disease", "symptom", "drug", "other"]


class ExtractedEntities(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)


def _get_primekg_driver() -> AsyncDriver:
    global _primekg_driver
    if _primekg_driver is None:
        _primekg_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _primekg_driver


async def _extract_entities(query: str) -> list[ExtractedEntity]:
    # `method="function_calling"` bắt buộc — mặc định (tự chọn theo model, thường ngả
    # về "json_schema" strict) làm proxy OpenRouter cho model hiện dùng
    # (`nvidia/nemotron-3-super-120b-a12b:free`, xem `app/core/config.py::AGENT_MODEL`)
    # trả response rỗng/`choices=None`, khiến `openai` SDK crash lúc parse
    # (`TypeError: 'NoneType' object is not iterable`) — đã verify "function_calling"
    # chạy ổn định với model này.
    model = get_model().with_structured_output(ExtractedEntities, method="function_calling")
    result = await model.ainvoke(
        [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=query)]
    )
    assert isinstance(result, ExtractedEntities)
    return result.entities


async def _search_primekg(names: list[str], entity_limit: int = 5, rel_limit: int = 30) -> list[dict[str, Any]]:
    if not names:
        return []
    driver = _get_primekg_driver()
    async with driver.session() as session:
        result = await session.run(
            _PRIMEKG_SEARCH_QUERY,
            names=names,
            allowed_rels=_PRIMEKG_ALLOWED_RELS,
            entity_limit=entity_limit,
            rel_limit=rel_limit,
        )
        return [r.data() async for r in result]


@tool
async def ground_medical_entities(query: str) -> str:
    """Chuyển câu hỏi tự nhiên của người dùng thành CONTEXT y khoa có cấu trúc (JSON):
    trích xuất từng thực thể (bệnh/triệu chứng/thuốc) nhắc tới trong câu hỏi, chuẩn hoá
    qua DermO (id/định nghĩa/từ đồng nghĩa), rồi dùng các từ đồng nghĩa đó search PrimeKG
    lấy quan hệ lâm sàng liên quan (triệu chứng đi kèm, thuốc chỉ định/chống chỉ định,
    bệnh dễ nhầm lẫn). BẮT BUỘC gọi tool này TRƯỚC khi trả lời câu hỏi có nhắc tới bệnh/
    triệu chứng/thuốc cụ thể — CHỈ được khẳng định fact y khoa dựa trên dữ liệu JSON trả
    về, KHÔNG dùng kiến thức nền riêng của model cho phần này. Thực thể không tra được
    (`dermo: null`, `primekg_relations: []`) nghĩa là KHÔNG có dữ liệu trong phạm vi được
    cung cấp — phải nói rõ điều đó thay vì suy đoán.

    Args:
        query: Câu hỏi/mô tả gốc của người dùng (tiếng Việt hoặc tiếng Anh đều được).
    """
    entities = await _extract_entities(query)
    if not entities:
        return json.dumps(
            {"entities": [], "note": "Không trích xuất được thực thể y khoa nào từ câu hỏi."},
            ensure_ascii=False,
        )

    grounded: list[dict[str, Any]] = []
    for entity in entities:
        # DermO là ontology BỆNH/TRIỆU CHỨNG (xem `data/dermo/dermatology.obo`), không
        # phải ontology thuốc — map `type == "drug"` qua đây dễ khớp nhầm (vd "aspirin"
        # từng khớp nhầm "aspirin burn", 1 bệnh lý bỏng do hoá chất, không phải thuốc).
        # Thực thể `drug` search PrimeKG thẳng bằng tên gốc, bỏ qua bước chuẩn hoá DermO.
        dermo_records = await search_dermo_terms(entity.text, limit=1) if entity.type != "drug" else []
        dermo_info: dict[str, Any] | None = None
        search_names = [entity.text]

        if dermo_records:
            record = dermo_records[0]
            dermo_info = {
                "id": record["id"],
                "name": record["name"],
                "def": record.get("def"),
                "synonyms": record.get("synonyms") or [],
                "parents": record.get("parents") or [],
            }
            search_names = list({entity.text, record["name"], *dermo_info["synonyms"]})

        relations = await _search_primekg(search_names)

        grounded.append(
            {
                "text": entity.text,
                "type": entity.type,
                "dermo": dermo_info,
                "primekg_relations": relations,
            }
        )

    return json.dumps({"entities": grounded}, ensure_ascii=False, indent=2)
