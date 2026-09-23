#!/usr/bin/env python3
"""Gắn `dermo_id` (DermO ontology id, vd "DERMO:0000811") vào mỗi bệnh trong
`01_normalize/output/diseases/*.json` — cầu nối ID-based DUY NHẤT hiện có giữa 3 nguồn dữ
liệu độc lập của hệ thống:
  - Neo4j `:DermoTerm.id`   (dùng bởi `app/agent/tools/entity_grounding.py::_search_primekg`,
    trả trong field `dermo.id` của kết quả `ground_medical_entities`)
  - Neo4j `:Entity` (PrimeKG) — gián tiếp qua DermO (PrimeKG search dùng tên/synonym DermO)
  - Qdrant KB guideline (`disease_id`, dùng bởi `get_disease_guideline_profile`)

Trước script này, 3 nguồn KHÔNG chia sẻ id nào — nối duy nhất là LLM tự diễn giải tên bệnh
sang câu hỏi tiếng Việt rồi semantic search KB (không chính xác, không kiểm chứng được).
Sau script này, `app/agent/tools/entity_grounding.py` có thể tra thẳng
`dermo_id -> disease_id` (`knowledge_base_search.py::find_disease_id_by_dermo_id`, filter
cứng trên payload Qdrant) khi cả 2 phía cùng match được 1 DermO id — loại bỏ bước "model tự
đoán" cho đúng trường hợp này.

Cách match: so khớp CHÍNH XÁC (lowercase, sau khi tách theo "/" và ",") giữa
`english_name`/`name` của từng bệnh trong KB với `dermo/output/dermo_term_map.json` (map
tên + đồng nghĩa DermO -> id, đã build sẵn bởi `dermo/scripts/01_process_dermo_ontology.py`).
CHỦ Ý không dùng fuzzy/substring match — 1 kết quả sai (vd match nhầm bệnh khác) sẽ khiến
agent lấy guideline SAI mà không biết, worse than không match được (fallback về semantic
search như cũ, tool vẫn tự nói rõ "không match").

Input : dermo/output/dermo_term_map.json
        01_normalize/output/diseases/*.json  (đã có sau khi chạy 01_normalize_diseases.py)
Output: ghi đè lại CHÍNH 01_normalize/output/diseases/*.json, thêm field `dermo_id`
        (str hoặc None) vào mỗi bệnh.

Chạy: python data-ingest/01_normalize/scripts/04_link_dermo_ids.py [-v]
"""
import json
import re
import sys
from pathlib import Path

INGEST_DIR = Path(__file__).resolve().parents[2]
DISEASES_DIR = Path(__file__).resolve().parents[1] / "output" / "diseases"
TERM_MAP_PATH = INGEST_DIR / "dermo" / "output" / "dermo_term_map.json"

VERBOSE = "-v" in sys.argv


def _candidates(disease: dict) -> list[str]:
    names: list[str] = []
    english_name = disease.get("english_name", "")
    if english_name:
        names.append(english_name)
        names.extend(re.split(r"[/,]", english_name))
    name = disease.get("name", "")
    if name:
        names.append(name)
    seen: list[str] = []
    for n in names:
        n = n.strip()
        if n and n not in seen:
            seen.append(n)
    return seen


def main() -> int:
    if not TERM_MAP_PATH.exists():
        print(f"[lỗi] không thấy {TERM_MAP_PATH} — chạy nguồn `dermo` trước (xem run.py)")
        return 1
    term_map: dict[str, str] = json.loads(TERM_MAP_PATH.read_text(encoding="utf-8"))

    if not DISEASES_DIR.exists() or not any(DISEASES_DIR.glob("*.json")):
        print(f"[lỗi] {DISEASES_DIR} trống — chạy 01_normalize_diseases.py trước")
        return 1

    total = 0
    matched = 0
    unmatched: list[str] = []

    for path in sorted(DISEASES_DIR.glob("*.json")):
        items = json.loads(path.read_text(encoding="utf-8"))
        for d in items:
            total += 1
            dermo_id = None
            matched_via = None
            for candidate in _candidates(d):
                key = candidate.lower().strip()
                if key in term_map:
                    dermo_id = term_map[key]
                    matched_via = candidate
                    break
            d["dermo_id"] = dermo_id
            if dermo_id:
                matched += 1
                if VERBOSE:
                    print(f"  [ok] {d.get('id')} -> {dermo_id} (khớp \"{matched_via}\")")
            else:
                unmatched.append(f"{d.get('id')} ({d.get('english_name', d.get('name', '?'))})")

        path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Đã gắn dermo_id: {matched}/{total} bệnh khớp trực tiếp với DermO ontology.")
    if unmatched:
        print(f"{len(unmatched)} bệnh KHÔNG match được (giữ dermo_id=null, vẫn dùng semantic search như cũ):")
        for u in unmatched:
            print(f"  - {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
