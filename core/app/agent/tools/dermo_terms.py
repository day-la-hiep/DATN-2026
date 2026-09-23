"""Tool tra cứu KB thuật ngữ da liễu DermO — dữ liệu ontology (`data/dermo/
dermatology.obo`) đã trích xuất (`data/dermo/process_dermo_ontology.py`) và nạp sẵn vào
Neo4j (`data/dermo/load_to_neo4j.py`), label riêng `:DermoTerm` (KHÔNG lẫn với `:Entity`
của PrimeKG, xem docstring `load_to_neo4j.py`).

Khác `query_dermatology_kg` (`knowledge_graph.py`, LLM tự sinh Cypher cho câu hỏi mở):
đây là tra cứu TỪ ĐIỂN thuật ngữ — input 1 tên/biến thể bệnh da liễu, output thẳng
id/định nghĩa/từ đồng nghĩa/thuật ngữ cha (is_a) chuẩn hoá trong ontology. Cypher CỐ ĐỊNH
(CONTAINS trên `name` + `synonyms`), không qua LLM sinh Cypher — rẻ, nhanh, không rủi ro
sinh sai truy vấn cho 1 thao tác tra từ điển đơn giản.
"""
from typing import Any

from langchain_core.tools import tool
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings

_driver: AsyncDriver | None = None

# `WITH t, ... ` giữa mỗi `OPTIONAL MATCH` để mở rộng TUẦN TỰ (parents rồi related) thay
# vì gộp chung — tránh cross join nhân đôi kết quả khi 1 term vừa có nhiều `is_a` vừa có
# nhiều quan hệ khác. `LIMIT` áp ngay sau khi lọc term khớp (trước khi mở rộng quan hệ)
# để giới hạn đúng SỐ TERM trả về, không phải số dòng sau join.
#
# `match_rank` ưu tiên khớp CHÍNH XÁC (0) trước khớp CONTAINS (1) — thiếu bước này, term
# ngắn/phổ biến (vd "acne") có thể bị `LIMIT` cắt mất trước khi tới đúng term chính xác,
# trả nhầm 1 term khác chỉ tình cờ chứa chuỗi đó trong tên/synonym (vd "neonatal cephalic
# pustulosis", synonym "neonatal acne" — đã verify xảy ra thật khi `limit=1`). Quan trọng
# với `entity_grounding.py`: `dermo.id` sai sẽ khiến `kb_disease_id` (cầu nối sang
# guideline KB) tra nhầm/không tìm thấy dù bệnh đó CÓ trong KB.
_LOOKUP_QUERY = """
MATCH (t:DermoTerm)
WHERE NOT t.is_obsolete
  AND (toLower(t.name) CONTAINS toLower($term)
       OR any(syn IN coalesce(t.synonyms, []) WHERE toLower(syn) CONTAINS toLower($term)))
WITH DISTINCT t,
     CASE
       WHEN toLower(t.name) = toLower($term)
            OR any(syn IN coalesce(t.synonyms, []) WHERE toLower(syn) = toLower($term))
       THEN 0 ELSE 1
     END AS match_rank
ORDER BY match_rank, size(t.name)
LIMIT $limit
OPTIONAL MATCH (t)-[:IS_A]->(parent:DermoTerm)
WITH t, match_rank, collect(DISTINCT parent.name) AS parents
OPTIONAL MATCH (t)-[rel]->(related:DermoTerm)
WHERE type(rel) <> 'IS_A'
WITH t, match_rank, parents, collect(DISTINCT {type: type(rel), name: related.name}) AS related
RETURN t.id AS id, t.name AS name, t.def AS def, t.synonyms AS synonyms,
       t.xrefs AS xrefs, parents, related
ORDER BY match_rank
"""


def _get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _driver


def _format_record(row: dict[str, Any]) -> str:
    lines = [f"{row['id']} — {row['name']}"]
    if row.get("def"):
        lines.append(f"  Định nghĩa: {row['def']}")
    if row.get("synonyms"):
        lines.append(f"  Từ đồng nghĩa: {', '.join(row['synonyms'])}")
    if row.get("parents"):
        lines.append(f"  Thuộc nhóm (is_a): {', '.join(row['parents'])}")

    grouped: dict[str, list[str]] = {}
    for rel in row.get("related") or []:
        if rel.get("name"):
            grouped.setdefault(rel["type"], []).append(rel["name"])
    for rel_type, names in grouped.items():
        lines.append(f"  {rel_type}: {', '.join(names)}")

    if row.get("xrefs"):
        lines.append(f"  Xref: {', '.join(row['xrefs'])}")
    return "\n".join(lines)


async def search_dermo_terms(term: str, limit: int = 5) -> list[dict[str, Any]]:
    """Chạy thẳng `_LOOKUP_QUERY`, trả về record thô (không format text) — dùng lại bởi
    `lookup_dermo_term` (tool) và `entity_grounding.py` (pipeline extract -> normalize ->
    search PrimeKG, cần dữ liệu có cấu trúc chứ không phải text tự do)."""
    driver = _get_driver()
    async with driver.session() as session:
        result = await session.run(_LOOKUP_QUERY, term=term, limit=limit)
        return [r.data() async for r in result]


@tool
async def lookup_dermo_term(term: str, limit: int = 5) -> str:
    """Tra cứu 1 thuật ngữ/tên bệnh da liễu trong ontology DermO để CHUẨN HOÁ về khái
    niệm chuẩn — trả về id, định nghĩa, từ đồng nghĩa, thuật ngữ cha (is_a) và quan hệ
    khác (vd has_symptom, results_in) nếu có. Dùng khi cần biết 1 thuật ngữ da liễu có
    đúng nghĩa gì, thuộc nhóm bệnh nào, hoặc có tên gọi khác nào không — KHÔNG dùng cho
    câu hỏi phức tạp về quan hệ bệnh-thuốc-triệu chứng (dùng `query_dermatology_kg` cho
    việc đó).

    Args:
        term: Tên bệnh/thuật ngữ da liễu cần tra (tiếng Anh, có thể là tên đầy đủ hoặc
            1 phần, vd "psoriasis", "harlequin baby").
        limit: Số kết quả tối đa trả về (mặc định 5).
    """
    records = await search_dermo_terms(term, limit=limit)

    if not records:
        return f"Không tìm thấy thuật ngữ da liễu nào khớp với '{term}' trong DermO."

    return "\n\n".join(_format_record(r) for r in records)
