"""Tool `expand_entity_context` — từ thực thể đã grounding, mở rộng graph PrimeKG để tìm
ỨNG VIÊN bệnh liên quan rồi tra guideline theo TỪNG ứng viên (không chỉ theo câu hỏi gốc).

Vì sao cần: `search_disease_guidelines` chỉ semantic search theo câu hỏi gốc của người dùng,
nên bệnh dễ nhầm lẫn/cùng triệu chứng mà câu hỏi không nhắc tên thì không bao giờ được tra.
`ground_medical_entities` chỉ trả quan hệ 1 bước quanh thực thể. Tool này đi tiếp:

  1. Tìm nút PrimeKG khớp từng thực thể (tên + từ đồng nghĩa DermO).
  2. Từ các nút đó (triệu chứng/bệnh/thuốc) lan ra BỆNH ứng viên, có điểm:
       - triệu chứng -> bệnh có triệu chứng đó (`DISEASE_PHENOTYPE_POSITIVE`), trọng số theo
         độ đặc hiệu của triệu chứng (triệu chứng càng hiếm càng nặng);
       - bệnh -> bệnh liên quan (`DISEASE_DISEASE`);
       - bệnh -> triệu chứng của nó -> bệnh khác cùng triệu chứng (2-hop, trọng số nhỏ);
       - thuốc -> bệnh được chỉ định (`INDICATION`).
  3. Ứng viên nào nối được sang guideline KB (DermO id khớp CHÍNH XÁC -> `kb_disease_id`, cùng
     cầu nối `ground_medical_entities` dùng) được cộng điểm và kèm đoạn guideline ngắn
     (overview + differential) làm context. Không có liên kết thì KHÔNG đoán bằng semantic
     search — `kb_disease_id: null`, agent tự quyết có tra tiếp hay không.

Điểm graph chỉ là heuristic xếp hạng để chọn ứng viên đáng xem, KHÔNG phải xác suất chẩn đoán.
"""
import asyncio
import json
import re
from typing import Any, LiteralString

from langchain_core.tools import tool

from agent.tools.dermo_terms import get_driver, search_dermo_terms
from app.infra.qdrant_client import (
    get_kb_chunks_by_disease_id,
    get_kb_disease_id_by_dermo_id,
)

_MAX_INPUTS = 6
_SHARED_CAP = 2.0  # trần điểm 2-hop: bệnh nhiều triệu chứng chung (toàn thân) không được lấn át tín hiệu trực tiếp
_POOL = 12  # số ứng viên lấy từ graph trước khi nối guideline và xếp hạng lại
_KB_BONUS = 1.0  # cộng cho ứng viên có guideline trong KB: có bằng chứng để đưa vào context
_GUIDELINE_CHUNKS = ("overview", "differential")
_CHUNK_MAX_CHARS = 500
_SEED_TYPES = ["disease", "effect/phenotype", "drug"]

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

_EXACT_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) IN $names
RETURN elementId(n) AS id, n.name AS name, n.type AS type
"""

_LOOSE_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) CONTAINS $name
RETURN elementId(n) AS id, n.name AS name, n.type AS type
ORDER BY size(n.name)
LIMIT 3
"""


async def _run(query: LiteralString, **params: Any) -> list[dict[str, Any]]:
    async with get_driver().session() as session:  # pyright: ignore[reportUnknownMemberType]
        result = await session.run(query, **params)
        return [r.data() async for r in result]


def _base_name(name: str) -> str:
    """Bỏ hậu tố kiểu " (disease)" mà PrimeKG gắn vào nút trùng tên."""
    return re.sub(r"\s*\((?:disease|disorder)\)$", "", name.strip().lower())


def _name_variants(name: str) -> list[str]:
    """PrimeKG đảo tên kiểu "dermatitis, atopic"; DermO dùng "atopic dermatitis"."""
    parts = [p.strip() for p in name.split(",")]
    return [name, " ".join(reversed(parts))] if len(parts) == 2 else [name]


async def _exact_dermo(name: str) -> dict[str, Any] | None:
    """Chỉ nhận DermO term khớp CHÍNH XÁC (tên hoặc từ đồng nghĩa) — `search_dermo_terms`
    còn trả kết quả CONTAINS, mà `dermo_id` sai sẽ nối nhầm sang guideline bệnh khác."""
    for variant in _name_variants(name):
        records = await search_dermo_terms(variant, limit=1)
        if not records:
            continue
        record = records[0]
        known = {str(record["name"]).lower(), *(s.lower() for s in record.get("synonyms") or [])}
        if variant.lower() in known:
            return record
    return None


async def _resolve_seeds(
    entities: list[str],
) -> tuple[list[dict[str, Any]], list[str], set[str]]:
    """Trả (các nút PrimeKG khớp, input không khớp nút nào, DermO id của các input)."""
    seeds: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    dermo_ids: set[str] = set()
    for entity in entities:
        names = {entity.lower()}
        record = await _exact_dermo(entity)
        if record:
            dermo_ids.add(record["id"])
            names |= {str(record["name"]).lower(), *(s.lower() for s in record.get("synonyms") or [])}
        rows = await _run(_EXACT_SEED_QUERY, types=_SEED_TYPES, names=sorted(names))
        if not rows:
            rows = await _run(_LOOSE_SEED_QUERY, types=_SEED_TYPES, name=entity.lower())
        if not rows:
            unmatched.append(entity)
        for row in rows:
            seeds[row["id"]] = row
    return list(seeds.values()), unmatched, dermo_ids


def _trim(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _CHUNK_MAX_CHARS else text[: _CHUNK_MAX_CHARS - 1] + "…"


async def _attach_kb(candidate: dict[str, Any]) -> dict[str, Any]:
    dermo = await _exact_dermo(candidate["name"])
    candidate["dermo_id"] = dermo["id"] if dermo else None
    candidate["kb_disease_id"] = (
        await get_kb_disease_id_by_dermo_id(dermo["id"]) if dermo else None
    )
    return candidate


@tool
async def expand_entity_context(entities: list[str], top_n: int = 3) -> str:
    """Mở rộng thông tin từ các thực thể đã grounding: lan ra graph PrimeKG để tìm BỆNH ỨNG
    VIÊN liên quan (cùng triệu chứng, bệnh liên quan, bệnh mà thuốc chỉ định) rồi kèm đoạn
    guideline ngắn cho từng ứng viên có trong guideline KB. Gọi SAU `ground_medical_entities`
    khi chưa rõ ứng viên nào (vd chỉ có triệu chứng, hoặc cần bệnh dễ nhầm với bệnh nghi ngờ),
    để tra guideline theo ứng viên thay vì chỉ theo câu hỏi gốc. Gọi 1 lần cho cả danh sách
    thực thể, không gọi lặp lại y hệt.

    Kết quả là gợi ý để xem xét, KHÔNG phải chẩn đoán: `graph_score` chỉ xếp hạng độ liên
    quan trong đồ thị. Chỉ khẳng định fact y khoa dựa trên `guideline` kèm theo hoặc
    `get_disease_guideline_profile(kb_disease_id)`; ứng viên `kb_disease_id: null` chỉ có quan
    hệ đồ thị, chưa có bằng chứng guideline.

    Args:
        entities: Tên thực thể bằng TIẾNG ANH y khoa (lấy từ `text`/`dermo.name` trong kết quả
            `ground_medical_entities`): triệu chứng, bệnh hoặc thuốc. Tối đa 6.
        top_n: Số ứng viên trả về (1-5, mặc định 3).
    """
    entities = [e.strip() for e in entities if e.strip()][:_MAX_INPUTS]
    if not entities:
        return json.dumps({"candidates": [], "note": "Không có thực thể đầu vào."}, ensure_ascii=False)
    top_n = min(max(top_n, 1), 5)

    seeds, unmatched, seed_dermo_ids = await _resolve_seeds(entities)
    if not seeds:
        return json.dumps(
            {"candidates": [], "unmatched": unmatched,
             "note": "Không nút PrimeKG nào khớp các thực thể này."},
            ensure_ascii=False,
        )

    pool = await _run(_CANDIDATE_QUERY, seed_ids=[s["id"] for s in seeds], pool=_POOL, shared_cap=_SHARED_CAP)
    pool = list(await asyncio.gather(*(_attach_kb(c) for c in pool)))
    # PrimeKG có nút trùng cho cùng 1 bệnh (vd "atopic dermatitis" / "dermatitis, atopic"):
    # loại ứng viên chính là bệnh đầu vào, chỉ giữ bệnh KHÁC để mở rộng.
    input_names = {_base_name(n) for n in [*entities, *(s["name"] for s in seeds)]}
    pool = [
        c for c in pool
        if c["dermo_id"] not in seed_dermo_ids
        and not input_names & {_base_name(v) for v in _name_variants(c["name"])}
    ]
    for c in pool:
        c["graph_score"] = round(c.pop("score"), 2)
        c["_rank"] = c["graph_score"] + (_KB_BONUS if c["kb_disease_id"] else 0.0)
    ranked = sorted(pool, key=lambda c: c["_rank"], reverse=True)[:top_n]

    for c in ranked:
        c.pop("_rank")
        c["guideline"] = []
        if c["kb_disease_id"]:
            records = await get_kb_chunks_by_disease_id(c["kb_disease_id"])
            by_type = {(r.payload or {}).get("chunk_type"): r.payload or {} for r in records}
            c["guideline"] = [
                {"chunk_type": t, "text": _trim(str(by_type[t].get("text", ""))),
                 "source": by_type[t].get("source_label", "")}
                for t in _GUIDELINE_CHUNKS if t in by_type
            ]

    return json.dumps(
        {
            "seeds": [{"name": s["name"], "type": s["type"]} for s in seeds],
            "unmatched": unmatched,
            "candidates": ranked,
            "note": "graph_score là heuristic xếp hạng, không phải xác suất; xem tài liệu tool.",
        },
        ensure_ascii=False,
        indent=2,
    )
