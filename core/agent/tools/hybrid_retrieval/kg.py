"""Nhánh KG của `hybrid_retrieval`"""

import asyncio
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.common.llm import get_model
from app.api.deps import get_knowledge_graph_service
from app.services.knowledge_graph_service import base_name, name_variants

_MAX_INPUTS = 6  # số thực thể tối đa dùng làm hạt giống mở rộng ứng viên
_SHARED_CAP = 2.0  # trần điểm 2-hop: bệnh nhiều triệu chứng chung (toàn thân) không được lấn át tín hiệu trực tiếp
_POOL = 12  # số ứng viên lấy từ graph trước khi lọc bỏ chính bệnh đầu vào

# Trọng số (heuristic, xem docstring module). `3 / ln(2 + degree)`: triệu chứng nối với ít bệnh
# thì đặc hiệu hơn, đóng góp nhiều điểm hơn.
_CANDIDATE_QUERY = """
UNWIND $seed_ids AS sid
MATCH (s:Entity) WHERE elementId(s) = sid
WITH collect(s) AS seeds
CALL (seeds) {
  UNWIND seeds AS s
  WITH s WHERE s.type = 'effect/phenotype'
  MATCH (s)-[:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'})
  RETURN d, 3.0 / log(2.0 + COUNT { (s)--() }) AS w, 'direct' AS kind, 'triệu chứng: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'disease'
  MATCH (s)-[:DISEASE_DISEASE]-(d:Entity {type: 'disease'}) WHERE d <> s
  RETURN d, 1.0 AS w, 'direct' AS kind, 'bệnh liên quan tới: ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'disease'
  MATCH (s)-[:DISEASE_PHENOTYPE_POSITIVE]-(p:Entity {type: 'effect/phenotype'})
        -[:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'}) WHERE d <> s
  RETURN d, 1.5 / log(2.0 + COUNT { (p)--() }) AS w, 'shared' AS kind,
         'chung triệu chứng ' + p.name + ' với ' + s.name AS via
  UNION ALL
  UNWIND seeds AS s
  WITH s WHERE s.type = 'drug'
  MATCH (s)-[:INDICATION]-(d:Entity {type: 'disease'})
  RETURN d, 1.0 AS w, 'direct' AS kind, 'thuốc ' + s.name + ' chỉ định cho bệnh này' AS via
}
WITH d, seeds,
     sum(CASE kind WHEN 'direct' THEN w ELSE 0 END) AS direct,
     sum(CASE kind WHEN 'shared' THEN w ELSE 0 END) AS shared,
     collect(DISTINCT via)[..4] AS why
WHERE NOT d IN seeds
WITH d, why, direct + CASE WHEN shared > $shared_cap THEN $shared_cap ELSE shared END AS score
RETURN d.name AS name, score, why
ORDER BY score DESC
LIMIT $pool
"""


_EXTRACT_SYSTEM = (
    "Trích xuất các thực thể y khoa DA LIỄU (tên bệnh, triệu chứng, thuốc) được nhắc "
    "tới trong câu hỏi của người dùng. Dịch mỗi thực thể sang tên tiếng Anh y khoa chuẩn "
    "(dữ liệu tra cứu gốc là tiếng Anh, vd 'nổi mề đay' -> 'urticaria', 'da tôi đỏ và "
    "ngứa' -> 2 thực thể 'erythema' và 'pruritus'). CHỈ trích xuất thực thể RÕ RÀNG có "
    "trong câu hỏi — không suy đoán, không bổ sung thực thể không được nhắc tới. Nếu câu "
    "hỏi không chứa thực thể y khoa nào, trả về danh sách rỗng. Với mỗi thực thể, điền thêm tên "
    "tiếng Việt chuẩn trong sách giáo khoa da liễu (`vi`) để khớp từ khoá ở sách tiếng Việt."
)

# Chỉ giữ quan hệ có giá trị lâm sàng trực tiếp (khớp `ALLOWED_RELATION_TYPES` của `data_ingest` PrimeKG); bỏ nhiễu mức phân
# tử / tế bào (protein-protein, anatomy-protein...). Nhãn tiếng Việt trung tính về chiều vì truy vấn không phân biệt chiều cạnh.
_RELATION_LABELS = {
    "DISEASE_PHENOTYPE_POSITIVE": "bệnh–triệu chứng (có)",
    "DISEASE_PHENOTYPE_NEGATIVE": "bệnh–triệu chứng (không có)",
    "DISEASE_DISEASE": "bệnh liên quan",
    "INDICATION": "thuốc–bệnh (chỉ định)",
    "CONTRAINDICATION": "thuốc–bệnh (chống chỉ định)",
    "OFF_LABEL_USE": "thuốc–bệnh (dùng ngoài chỉ định)",
}
_RELATION_TYPES = list(_RELATION_LABELS)
_FACTS_PER_ENTITY = 8
_CANDIDATES = 3


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


class ExtractedEntity(BaseModel):
    text: str = Field(
        description="Tên bệnh/triệu chứng/thuốc bằng tiếng Anh y khoa chuẩn, dịch từ "
        "câu hỏi gốc nếu cần"
    )
    vi: str = Field(default="", description="Tên tiếng Việt chuẩn của thực thể (rỗng nếu không có)")
    type: Literal["disease", "symptom", "drug", "other"]


class ExtractedEntities(BaseModel):
    entities: list[ExtractedEntity] = Field(
        default_factory=lambda: list[ExtractedEntity]()
    )


async def extract_entities(query: str) -> list[ExtractedEntity]:
    # `method="function_calling"` bắt buộc — mặc định (tự chọn theo model, thường ngả
    # về "json_schema" strict) làm proxy OpenRouter cho model hiện dùng
    # (`nvidia/nemotron-3-super-120b-a12b:free`, xem `app/config/settings.py::AGENT_MODEL`)
    # trả response rỗng/`choices=None`, khiến `openai` SDK crash lúc parse
    # (`TypeError: 'NoneType' object is not iterable`) — đã verify "function_calling"
    # chạy ổn định với model này.
    model = get_model().with_structured_output(
        ExtractedEntities, method="function_calling"
    )
    result = await model.ainvoke(
        [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=query)]
    )
    assert isinstance(result, ExtractedEntities)
    return list(result.entities)


async def _search_primekg(
    names: list[str],
    allowed_rels: list[str],
    entity_limit: int = 5,
    rel_limit: int = 30,
) -> list[dict[str, Any]]:
    if not names:
        return []
    return await get_knowledge_graph_service().run(
        _PRIMEKG_SEARCH_QUERY,
        names=names,
        allowed_rels=allowed_rels,
        entity_limit=entity_limit,
        rel_limit=rel_limit,
    )


def _relation_fact(row: dict[str, Any]) -> str:
    label = _RELATION_LABELS.get(row["relation"], row["relation"])
    return f"{row['entity']} ({row['entity_type']}) — {label} — {row['related']} ({row['related_type']})"


async def _entity_facts(entity: ExtractedEntity) -> list[str]:
    """Quan hệ PrimeKG 1 bước quanh một thực thể"""
    names: list[str] = [entity.text]
    if entity.type != "drug":
        records = await get_knowledge_graph_service().search_dermo_terms(
            entity.text, limit=1
        )
        if records:
            names = list(
                {
                    entity.text,
                    records[0]["name"],
                    *(records[0].get("synonyms") or []),
                }
            )
    rows = await _search_primekg(
        names, _RELATION_TYPES, entity_limit=3, rel_limit=_FACTS_PER_ENTITY
    )
    return [_relation_fact(r) for r in rows]


async def _candidate_facts(entity_names: list[str]) -> list[str]:
    """Bệnh ứng viên lan ra từ graph (cùng triệu chứng, bệnh liên quan, thuốc chỉ định), loại chính bệnh đầu vào."""
    (
        seeds,
        _,
        seed_dermo_ids,
    ) = await get_knowledge_graph_service().resolve_seeds(entity_names)
    if not seeds:
        return []
    pool = await get_knowledge_graph_service().run(
        _CANDIDATE_QUERY,
        seed_ids=[s["id"] for s in seeds],
        pool=_POOL,
        shared_cap=_SHARED_CAP,
    )
    pool = list(
        await asyncio.gather(
            *(get_knowledge_graph_service().attach_dermo_id(c) for c in pool)
        )
    )
    # PrimeKG có nút trùng cho cùng một bệnh (vd "atopic dermatitis" / "dermatitis, atopic")
    input_names = {
        base_name(n) for n in [*entity_names, *(s["name"] for s in seeds)]
    }
    pool = [
        c
        for c in pool
        if c["dermo_id"] not in seed_dermo_ids
        and not input_names & {base_name(v) for v in name_variants(c["name"])}
    ]
    return [
        f"Bệnh ứng viên theo đồ thị tri thức: {c['name']} (điểm đồ thị {c['score']:.2f}; {'; '.join(c['why'])})"
        for c in pool[:_CANDIDATES]
    ]


async def kg_search(query: str, *, limit: int = 15, entities: list[ExtractedEntity] | None = None) -> list[str]:
    """Các câu văn ngắn rút từ PrimeKG / DermO liên quan câu hỏi; truyền `entities` để khỏi trích lại"""
    entities = (entities if entities is not None else await extract_entities(query))[:_MAX_INPUTS]
    if not entities:
        return []
    per_entity = await asyncio.gather(*(_entity_facts(e) for e in entities))
    candidates = (
        []
        if all(e.type == "other" for e in entities)
        else await _candidate_facts([e.text for e in entities])
    )
    facts: list[str] = []
    for fact in [*candidates, *(f for group in per_entity for f in group)]:
        if fact not in facts:
            facts.append(fact)
    return facts[:limit]
