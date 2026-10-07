"""Truy vấn knowledge graph da liễu trên Neo4j (PrimeKG + DermO) dùng chung cho tool: chuẩn hoá tên bệnh / triệu chứng qua DermO,
khớp thực thể với nút PrimeKG, gợi ý câu hỏi phân biệt giữa các bệnh. Xây trên `Neo4jClient` (`app/infra/neo4j_client.py`); Cypher
CỐ ĐỊNH, không qua LLM sinh Cypher. Dùng bởi `agent/tools/hybrid_retrieval/kg.py` và `agent/tools/reasoning.py`."""
import re
from typing import Any, LiteralString

from app.infra.neo4j_client import Neo4jClient

# `WITH t, ... ` giữa mỗi `OPTIONAL MATCH` để mở rộng TUẦN TỰ (parents rồi related) thay
# vì gộp chung — tránh cross join nhân đôi kết quả khi 1 term vừa có nhiều `is_a` vừa có
# nhiều quan hệ khác. `LIMIT` áp ngay sau khi lọc term khớp (trước khi mở rộng quan hệ)
# để giới hạn đúng SỐ TERM trả về, không phải số dòng sau join.
#
# `match_rank` ưu tiên khớp CHÍNH XÁC (0) trước khớp CONTAINS (1) — thiếu bước này, term
# ngắn/phổ biến (vd "acne") có thể bị `LIMIT` cắt mất trước khi tới đúng term chính xác,
# trả nhầm 1 term khác chỉ tình cờ chứa chuỗi đó trong tên/synonym (vd "neonatal cephalic
# pustulosis", synonym "neonatal acne" — đã verify xảy ra thật khi `limit=1`). Quan trọng
# với `attach_dermo_id`: `dermo.id` sai sẽ khiến ứng viên bị lọc nhầm / giữ nhầm so với bệnh đầu vào.
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


CHUNK_MAX_CHARS = 500
SEED_TYPES = ["disease", "effect/phenotype", "drug"]

EXACT_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) IN $names
RETURN elementId(n) AS id, n.name AS name, n.type AS type
"""

LOOSE_SEED_QUERY = """
MATCH (n:Entity)
WHERE n.type IN $types AND toLower(n.name) CONTAINS $name
RETURN elementId(n) AS id, n.name AS name, n.type AS type
ORDER BY size(n.name)
LIMIT 3
"""


def base_name(name: str) -> str:
    """Bỏ hậu tố kiểu " (disease)" mà PrimeKG gắn vào nút trùng tên."""
    return re.sub(r"\s*\((?:disease|disorder)\)$", "", name.strip().lower())


def name_variants(name: str) -> list[str]:
    """PrimeKG đảo tên kiểu "dermatitis, atopic"; DermO dùng "atopic dermatitis"."""
    parts = [p.strip() for p in name.split(",")]
    return [name, " ".join(reversed(parts))] if len(parts) == 2 else [name]


def trim(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= CHUNK_MAX_CHARS else text[: CHUNK_MAX_CHARS - 1] + "…"


# Phenotype của bệnh (kèm độ hiếm `degree`, phenotype nối càng ít nút càng đặc hiệu) để chọn câu hỏi phân biệt.
_DISEASE_PHENOTYPES_QUERY = """
MATCH (d:Entity {type: 'disease'}) WHERE d.id IN $dids
MATCH (d)-[:DISEASE_PHENOTYPE_POSITIVE]-(p:Entity {type: 'effect/phenotype'})
RETURN d.id AS did, p.id AS pid, p.name AS pname, COUNT { (p)--() } AS degree
"""


class KnowledgeGraphService:
    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    async def run(self, query: LiteralString, **params: Any) -> list[dict[str, Any]]:
        return await self._neo4j.run(query, **params)

    async def search_dermo_terms(self, term: str, limit: int = 5) -> list[dict[str, Any]]:
        """Record thô: id, tên, định nghĩa, từ đồng nghĩa, thuật ngữ cha."""
        return await self._neo4j.run(_LOOKUP_QUERY, term=term, limit=limit)

    async def exact_dermo(self, name: str) -> dict[str, Any] | None:
        """Chỉ nhận DermO term khớp CHÍNH XÁC (tên hoặc từ đồng nghĩa) — `search_dermo_terms` còn trả kết quả CONTAINS, mà
        `dermo_id` sai sẽ nối nhầm sang guideline bệnh khác."""
        for variant in name_variants(name):
            records = await self.search_dermo_terms(variant, limit=1)
            if not records:
                continue
            record = records[0]
            known = {str(record["name"]).lower(), *(s.lower() for s in record.get("synonyms") or [])}
            if variant.lower() in known:
                return record
        return None

    async def resolve_seeds(self, entities: list[str]) -> tuple[list[dict[str, Any]], list[str], set[str]]:
        """Trả (các nút PrimeKG khớp, input không khớp nút nào, DermO id của các input)."""
        seeds: dict[str, dict[str, Any]] = {}
        unmatched: list[str] = []
        dermo_ids: set[str] = set()
        for entity in entities:
            names = {entity.lower()}
            record = await self.exact_dermo(entity)
            if record:
                dermo_ids.add(record["id"])
                names |= {str(record["name"]).lower(), *(s.lower() for s in record.get("synonyms") or [])}
            rows = await self.run(EXACT_SEED_QUERY, types=SEED_TYPES, names=sorted(names))
            if not rows:
                rows = await self.run(LOOSE_SEED_QUERY, types=SEED_TYPES, name=entity.lower())
            if not rows:
                unmatched.append(entity)
            for row in rows:
                seeds[row["id"]] = row
        return list(seeds.values()), unmatched, dermo_ids

    async def attach_dermo_id(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Gắn `dermo_id` cho ứng viên bệnh (None nếu DermO không có term khớp chính xác)."""
        dermo = await self.exact_dermo(candidate["name"])
        candidate["dermo_id"] = dermo["id"] if dermo else None
        return candidate

    async def disease_ids_for(self, name: str) -> list[str]:
        """Tên bệnh -> `id` các nút disease PrimeKG (cùng một bệnh có thể có vài nút trùng)."""
        names = {v.lower() for v in name_variants(name)}
        dermo = await self.exact_dermo(name)
        if dermo:
            names |= {str(dermo["name"]).lower(), *(s.lower() for s in dermo.get("synonyms") or [])}
        rows = await self.run(EXACT_SEED_QUERY, types=["disease"], names=sorted(names))
        if not rows:
            rows = await self.run(LOOSE_SEED_QUERY, types=["disease"], name=name.lower())
        if not rows:
            return []
        found = await self.run("MATCH (n:Entity) WHERE elementId(n) IN $eids RETURN n.id AS id", eids=[r["id"] for r in rows])
        return [r["id"] for r in found]

    async def discriminating_questions(
        self, diseases: list[str], known_phenotype_ids: list[str] | None = None, top_k: int = 3
    ) -> dict[str, Any]:
        """Chọn phenotype nên HỎI tiếp để phân biệt các bệnh đang cân nhắc: phenotype có ở một số bệnh nhưng không ở các bệnh còn
        lại, ưu tiên cái chia nhóm gần đôi nhất (loại trừ được nhiều giả thuyết nhất dù trả lời có hay không). Bỏ qua phenotype
        đã biết. `record_reasoning` gọi khi `next_action="ask_user"`; agent tự diễn đạt thành câu hỏi tiếng Việt.

        Args:
            diseases: 2-5 tên bệnh tiếng Anh đang cân nhắc.
            known_phenotype_ids: `primekg_id` phenotype đã biết (có hoặc đã hỏi), để không hỏi lại.
            top_k: Số câu hỏi gợi ý (1-5).
        """
        names = list(dict.fromkeys(n.strip() for n in diseases if n.strip()))[:5]
        top_k = min(max(top_k, 1), 5)
        if len(names) < 2:
            return {"questions": [], "note": "Cần ít nhất 2 bệnh để phân biệt."}
        known = set(known_phenotype_ids or [])

        sets: dict[str, dict[str, str]] = {}
        unresolved: list[str] = []
        degree: dict[str, int] = {}
        for name in names:
            dids = await self.disease_ids_for(name)
            if not dids:
                unresolved.append(name)
                continue
            phenos: dict[str, str] = {}
            for r in await self.run(_DISEASE_PHENOTYPES_QUERY, dids=dids):
                phenos[r["pid"]] = r["pname"]
                degree[r["pid"]] = r["degree"]
            sets[name] = phenos

        if len(sets) < 2:
            return {"questions": [], "unresolved": unresolved, "note": "Không đủ bệnh khớp đồ thị để so sánh."}

        n = len(sets)
        pool = {pid: pname for phenos in sets.values() for pid, pname in phenos.items()}
        # Hoà điểm cân bằng -> ưu tiên phenotype phổ biến (degree cao): người dùng dễ trả lời được hơn phenotype hiếm / chuyên sâu
        # (vd xét nghiệm, bất thường nội tạng).
        scored: list[tuple[float, int, str]] = []
        for pid in pool:
            if pid in known:
                continue
            have = [d for d, p in sets.items() if pid in p]
            if 0 < len(have) < n:
                scored.append((min(len(have), n - len(have)) / n, degree.get(pid, 0), pid))
        scored.sort(reverse=True)

        return {
            "questions": [
                {
                    "primekg_id": pid,
                    "phenotype": pool[pid],
                    "present_in": [d for d, p in sets.items() if pid in p],
                    "absent_in": [d for d, p in sets.items() if pid not in p],
                }
                for _, _, pid in scored[:top_k]
            ],
            "unresolved": unresolved,
            "note": "Phenotype phân biệt theo dữ liệu đồ thị (thưa) — chỉ là gợi ý câu hỏi, hãy đối chiếu bằng `hybrid_retrieval`.",
        }
