"""Bộ tool chẩn đoán phân biệt dựa trên phenotype PrimeKG (Neo4j `:Entity`) + guideline KB.

2 tool + 1 hàm phối hợp theo luồng: mô tả tự do -> nút phenotype chuẩn -> xếp hạng bệnh -> câu hỏi
phân biệt tiếp theo. Cypher CỐ ĐỊNH (không qua LLM sinh Cypher), tái dùng helper của
`expand_context.py` (kết nối Neo4j, khớp DermO, nối `kb_disease_id`).

  - `describe_morphology`: embed mô tả -> Qdrant `derma_phenotypes`
    (`data-ingest/01_normalize/scripts/load_phenotypes.py`) -> phenotype + `primekg_id`.
  - `generate_differential`: từ `primekg_id` phenotype -> bệnh xếp hạng (đặc hiệu hoá theo
    độ hiếm của phenotype, trừ điểm cạnh PHENOTYPE_NEGATIVE / phenotype bệnh nhân KHÔNG có),
    kèm đoạn guideline để kiểm chứng.
  - `suggest_discriminating_questions` (hàm, không phải tool — gọi từ `record_reasoning`):
    phenotype chia đôi tốt nhất nhóm bệnh đang cân nhắc.

Phenotype PrimeKG chỉ có tên tiếng Anh, không có mã HPO — `primekg_id` là thuộc tính `id` của
nút, không phải mã HPO.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.tools.expand_context import (
    _EXACT_SEED_QUERY,
    _LOOSE_SEED_QUERY,
    _attach_kb,
    _base_name,
    _exact_dermo,
    _name_variants,
    _run,
    _trim,
)
from agent.llm import get_model
from agent.tools.knowledge_base_search import get_kb_embeddings
from app.infra.qdrant_client import (
    get_kb_chunks_by_disease_id,
    search_phenotypes,
)

# Điểm cosine tối thiểu để coi 1 phenotype là "khớp". MiniLM chỉ khớp bề mặt chữ nên điểm cao
# chưa chắc đúng nghĩa (đã thấy "asdfgh" -> 0.61): khớp thật thường >= 0.75 khi truy vấn là thuật
# ngữ HPO tiếng Anh chuẩn (bước `_to_hpo_terms`), vì vậy đặt ngưỡng cao.
_MORPHOLOGY_MIN_SCORE = 0.7
_KB_BONUS = 1.0  # cùng ý nghĩa `expand_context._KB_BONUS`: ứng viên có guideline để kiểm chứng
_TERMS_SYSTEM = (
    "Chuyển mô tả triệu chứng/tổn thương da (tiếng Việt hoặc Anh) thành 1-3 thuật ngữ y khoa "
    "tiếng Anh theo phong cách Human Phenotype Ontology (vd 'Pruritus', 'Scaling skin', "
    "'Erythematous plaque', 'Vesicle', 'Blistering', 'Alopecia'). Với mô tả có nhiều cách gọi, trả cả "
    "thuật ngữ đồng nghĩa (vd mụn nước -> 'Vesicle', 'Blistering of the skin'). Chỉ trả thuật ngữ "
    "diễn tả đúng điều được mô tả, không suy diễn chẩn đoán. Nếu đầu vào không phải mô tả "
    "triệu chứng, trả danh sách rỗng."
)
_MAX_IDS = 12
_DIFF_POOL = 15
_GUIDELINE_CHUNKS = ("symptoms", "differential")

# `3 / ln(2 + degree)` cùng công thức với `expand_context`: phenotype nối ít nút đặc hiệu hơn.
_POSITIVE_QUERY = """
MATCH (p:Entity {type: 'effect/phenotype'}) WHERE p.id IN $ids
MATCH (p)-[:DISEASE_PHENOTYPE_POSITIVE]-(d:Entity {type: 'disease'})
RETURN d.id AS did, d.name AS name, p.id AS pid, p.name AS pname,
       3.0 / log(2.0 + COUNT { (p)--() }) AS w
"""

_NEGATIVE_QUERY = """
MATCH (p:Entity {type: 'effect/phenotype'}) WHERE p.id IN $ids
MATCH (p)-[:DISEASE_PHENOTYPE_NEGATIVE]-(d:Entity {type: 'disease'})
WHERE d.id IN $dids
RETURN d.id AS did, p.name AS pname, 3.0 / log(2.0 + COUNT { (p)--() }) AS w
"""

# Phenotype của bệnh mà bệnh nhân CHƯA có (để gợi ý điều còn thiếu) — lấy cả độ hiếm để ưu tiên.
_DISEASE_PHENOTYPES_QUERY = """
MATCH (d:Entity {type: 'disease'}) WHERE d.id IN $dids
MATCH (d)-[:DISEASE_PHENOTYPE_POSITIVE]-(p:Entity {type: 'effect/phenotype'})
RETURN d.id AS did, p.id AS pid, p.name AS pname, COUNT { (p)--() } AS degree
"""


class _HpoTerms(BaseModel):
    terms: list[str] = Field(default_factory=lambda: list[str]())


async def _to_hpo_terms(description: str) -> list[str]:
    """LLM chuẩn hoá mô tả tự do -> thuật ngữ HPO tiếng Anh (embedding MiniLM yếu với từ đồng
    nghĩa/tiếng Việt). Lỗi LLM -> dùng luôn mô tả gốc (giảm độ chính xác chứ không hỏng tool).
    `method="function_calling"` vì lý do như `entity_grounding._extract_entities`."""
    try:
        model = get_model().with_structured_output(
            _HpoTerms, method="function_calling"
        )
        result = await model.ainvoke(
            [
                SystemMessage(content=_TERMS_SYSTEM),
                HumanMessage(content=description),
            ]
        )
        assert isinstance(result, _HpoTerms)
        return [t.strip() for t in result.terms if t.strip()][:3]
    except Exception as exc:  # noqa: BLE001
        print(f"[describe_morphology] chuẩn hoá LLM lỗi, dùng mô tả gốc: {exc}")
        return [description]


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool
async def describe_morphology(description: str, top_k: int = 5) -> str:
    """Chuẩn hoá mô tả tổn thương/triệu chứng viết TỰ DO (tiếng Việt hoặc Anh) thành các
    phenotype chuẩn trong đồ thị PrimeKG (kèm `primekg_id`) — bước đầu để đưa vào
    `generate_differential`. Gọi MỖI mô tả riêng lẻ (vd "ngứa", "mụn nước ở kẽ ngón tay") thay
    vì 1 câu dài chứa nhiều triệu chứng, để mỗi triệu chứng ra đúng phenotype của nó. Kết quả
    dưới ngưỡng liên quan bị loại; không có kết quả nào -> mô tả chưa khớp phenotype nào, hãy
    hỏi lại người dùng bằng từ khác hoặc thử tiếng Anh y khoa.

    Args:
        description: 1 triệu chứng/đặc điểm tổn thương, vd "vảy trắng bạc", "erythematous
            plaques".
        top_k: Số phenotype tối đa trả về (1-10, mặc định 5).
    """
    top_k = min(max(top_k, 1), 10)
    terms = await _to_hpo_terms(description)
    if not terms:
        return _dumps(
            {"matches": [], "note": "Đầu vào không phải mô tả triệu chứng."}
        )
    embeddings = get_kb_embeddings()
    best: dict[str, Any] = {}
    for term in terms:
        vector = await embeddings.aembed_query(term)
        for m in await search_phenotypes(vector=vector, limit=top_k):
            pid = str((m.payload or {}).get("primekg_id"))
            if pid not in best or m.score > best[pid].score:
                best[pid] = m
    kept = sorted(
        (m for m in best.values() if m.score >= _MORPHOLOGY_MIN_SCORE),
        key=lambda m: m.score,
        reverse=True,
    )[:top_k]
    if not kept:
        return _dumps(
            {
                "matches": [],
                "note": "Không phenotype nào đủ khớp — hỏi lại/diễn đạt khác.",
            }
        )
    return _dumps(
        {
            "normalized_terms": terms,
            "matches": [
                {
                    "primekg_id": (m.payload or {}).get("primekg_id"),
                    "name": (m.payload or {}).get("name"),
                    "score": round(m.score, 2),
                }
                for m in kept
            ],
            "note": "score là độ tương đồng ngữ nghĩa, không phải xác suất. Chọn phenotype "
            "đúng với điều người dùng mô tả, bỏ phenotype lệch nghĩa.",
        }
    )


def _dedupe_by_name(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PrimeKG có nút trùng cho cùng 1 bệnh (vd "atopic dermatitis"/"dermatitis, atopic"):
    giữ ứng viên điểm cao nhất mỗi tên chuẩn hoá."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = min(_base_name(v) for v in _name_variants(row["name"]))
        if key not in best or row["score"] > best[key]["score"]:
            best[key] = row
    return sorted(best.values(), key=lambda r: r["score"], reverse=True)


async def _guideline_snippets(kb_disease_id: str) -> list[dict[str, str]]:
    records = await get_kb_chunks_by_disease_id(kb_disease_id)
    by_type = {
        (r.payload or {}).get("chunk_type"): r.payload or {} for r in records
    }
    return [
        {
            "chunk_type": t,
            "text": _trim(str(by_type[t].get("text", ""))),
            "source": str(by_type[t].get("source_label", "")),
        }
        for t in _GUIDELINE_CHUNKS
        if t in by_type
    ]


@tool
async def generate_differential(
    phenotype_ids: list[str],
    absent_phenotype_ids: list[str] | None = None,
    top_n: int = 5,
) -> str:
    """Xếp hạng các bệnh da liễu phù hợp với tập phenotype của bệnh nhân (`primekg_id` lấy từ
    `describe_morphology`). Điểm ưu tiên phenotype ĐẶC HIỆU (nối ít bệnh), trừ điểm bệnh có
    quan hệ phủ định với phenotype bệnh nhân CÓ, và bệnh mà phenotype bệnh nhân KHÔNG có lại là
    đặc trưng. Ứng viên có guideline trong KB kèm đoạn `symptoms`/`differential` để KIỂM CHỨNG
    — chỉ khẳng định khi guideline đó thật sự khớp mô tả; ứng viên `kb_disease_id: null` chỉ có
    quan hệ đồ thị, chưa kiểm chứng guideline.

    Kết quả là danh sách giả thuyết để xem xét, KHÔNG phải chẩn đoán; `score` là heuristic xếp
    hạng, không phải xác suất. `missing_common` là phenotype của bệnh mà bệnh nhân chưa nêu — dùng
    để đặt câu hỏi tiếp.

    Args:
        phenotype_ids: `primekg_id` các phenotype bệnh nhân CÓ (tối đa 12).
        absent_phenotype_ids: `primekg_id` các phenotype đã xác nhận bệnh nhân KHÔNG có.
        top_n: Số bệnh trả về (1-8, mặc định 5).
    """
    ids = list(dict.fromkeys(i.strip() for i in phenotype_ids if i.strip()))[
        :_MAX_IDS
    ]
    absent = list(dict.fromkeys((absent_phenotype_ids or [])))[:_MAX_IDS]
    top_n = min(max(top_n, 1), 8)
    if not ids:
        return _dumps({"candidates": [], "note": "Thiếu phenotype_ids."})

    rows = await _run(_POSITIVE_QUERY, ids=ids)
    if not rows:
        return _dumps(
            {
                "candidates": [],
                "note": "Không bệnh nào nối với các phenotype này trong đồ thị.",
            }
        )

    diseases: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = diseases.setdefault(
            r["did"],
            {"did": r["did"], "name": r["name"], "score": 0.0, "matched": {}},
        )
        if r["pid"] not in d["matched"]:
            d["matched"][r["pid"]] = r["pname"]
            d["score"] += r["w"]

    dids = list(diseases)
    for r in await _run(_NEGATIVE_QUERY, ids=ids, dids=dids):
        diseases[r["did"]]["score"] -= 2 * r["w"]
    if absent:
        for r in await _run(_POSITIVE_QUERY, ids=absent):
            if r["did"] in diseases:
                diseases[r["did"]]["score"] -= r[
                    "w"
                ]  # bệnh cần phenotype bệnh nhân không có

    ranked = [
        d
        for d in _dedupe_by_name(list(diseases.values()))
        if not d["name"].startswith("obsolete")
    ][:_DIFF_POOL]
    for d in ranked:
        await _attach_kb(d)
        d["rank"] = d["score"] + (_KB_BONUS if d["kb_disease_id"] else 0.0)
    ranked.sort(key=lambda d: d["rank"], reverse=True)
    pheno_rows = await _run(
        _DISEASE_PHENOTYPES_QUERY, dids=[d["did"] for d in ranked]
    )
    by_disease: dict[str, list[dict[str, Any]]] = {}
    for r in pheno_rows:
        by_disease.setdefault(r["did"], []).append(r)

    out: list[dict[str, Any]] = []
    for d in ranked:
        if d["score"] <= 0:
            continue  # điểm đã trừ phủ định/vắng mặt
        phenos = by_disease.get(d["did"], [])
        missing = sorted(
            (p for p in phenos if p["pid"] not in d["matched"]),
            key=lambda p: p["degree"],
        )
        missing_names = list(dict.fromkeys(p["pname"] for p in missing))[:5]
        out.append(
            {
                "name": d["name"],
                "score": round(d["score"], 2),
                "coverage": f"{len(d['matched'])}/{len(ids)}",
                "matched": sorted(d["matched"].values()),
                "missing_common": missing_names,
                "dermo_id": d["dermo_id"],
                "kb_disease_id": d["kb_disease_id"],
            }
        )
    out = out[:top_n]

    for c in out:
        c["guideline"] = (
            await _guideline_snippets(c["kb_disease_id"])
            if c["kb_disease_id"]
            else []
        )

    return _dumps(
        {
            "candidates": out,
            "note": "Giả thuyết để xem xét, không phải chẩn đoán. Kiểm chứng bằng guideline; "
            "ứng viên kb_disease_id=null chưa có bằng chứng guideline.",
        }
    )


async def _disease_ids_for(name: str) -> list[str]:
    """Tên bệnh -> `id` các nút disease PrimeKG (cùng 1 bệnh có thể có vài nút trùng)."""
    names = {v.lower() for v in _name_variants(name)}
    dermo = await _exact_dermo(name)
    if dermo:
        names |= {
            str(dermo["name"]).lower(),
            *(s.lower() for s in dermo.get("synonyms") or []),
        }
    rows = await _run(_EXACT_SEED_QUERY, types=["disease"], names=sorted(names))
    if not rows:
        rows = await _run(
            _LOOSE_SEED_QUERY, types=["disease"], name=name.lower()
        )
    if not rows:
        return []
    found = await _run(
        "MATCH (n:Entity) WHERE elementId(n) IN $eids RETURN n.id AS id",
        eids=[r["id"] for r in rows],
    )
    return [r["id"] for r in found]


async def suggest_discriminating_questions(
    diseases: list[str], known_phenotype_ids: list[str] | None = None, top_k: int = 3
) -> dict[str, Any]:
    """Chọn phenotype nên HỎI tiếp để phân biệt các bệnh đang cân nhắc: phenotype có ở một số
    bệnh nhưng không ở các bệnh còn lại, ưu tiên cái chia nhóm gần đôi nhất (loại trừ được nhiều
    giả thuyết nhất dù trả lời có hay không). Bỏ qua phenotype đã biết.

    KHÔNG phải `@tool`: được `record_reasoning` (`reasoning.py`) gọi khi `next_action="ask_user"`,
    gộp gợi ý vào kết quả lập luận — agent tự diễn đạt thành câu hỏi tiếng Việt rồi `ask_user`.

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
        dids = await _disease_ids_for(name)
        if not dids:
            unresolved.append(name)
            continue
        phenos: dict[str, str] = {}
        for r in await _run(_DISEASE_PHENOTYPES_QUERY, dids=dids):
            phenos[r["pid"]] = r["pname"]
            degree[r["pid"]] = r["degree"]
        sets[name] = phenos

    if len(sets) < 2:
        return {
            "questions": [],
            "unresolved": unresolved,
            "note": "Không đủ bệnh khớp đồ thị để so sánh.",
        }

    n = len(sets)
    pool = {
        pid: pname for phenos in sets.values() for pid, pname in phenos.items()
    }
    # Hoà điểm cân bằng -> ưu tiên phenotype phổ biến (degree cao): người dùng dễ trả lời được
    # hơn phenotype hiếm/chuyên sâu (vd xét nghiệm, bất thường nội tạng).
    scored: list[tuple[float, int, str]] = []
    for pid in pool:
        if pid in known:
            continue
        have = [d for d, p in sets.items() if pid in p]
        if 0 < len(have) < n:
            balance = min(len(have), n - len(have)) / n
            scored.append((balance, degree.get(pid, 0), pid))
    scored.sort(reverse=True)

    questions = [
        {
            "primekg_id": pid,
            "phenotype": pool[pid],
            "present_in": [d for d, p in sets.items() if pid in p],
            "absent_in": [d for d, p in sets.items() if pid not in p],
        }
        for _, _, pid in scored[:top_k]
    ]
    return {
        "questions": questions,
        "unresolved": unresolved,
        "note": "Phenotype phân biệt theo dữ liệu đồ thị (thưa) — chỉ là gợi ý câu hỏi, "
        "hãy đối chiếu tiêu chí phân biệt trong guideline.",
    }
