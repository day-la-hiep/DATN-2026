#!/usr/bin/env python3
"""Chuẩn hoá các nguồn guideline bệnh da liễu về 1 schema chung.

Input : byt/output/pdf_guideline_2015.json
        who/output/who_skin_diseases.json
        medlineplus/output/medlineplus_skin_conditions.json
Output: 01_normalize/output/diseases/<tên file gốc>.json  (giữ nguyên tên file — chunk builder
        `knowledge_base/scripts/build_chunks_kb2.py` lấy tên file làm `source_file`)

Việc làm:
  - kiểm tra đủ field bắt buộc + đúng kiểu (str / list[str]); thiếu field list -> [];
  - strip khoảng trắng, bỏ phần tử rỗng/trùng trong các field list;
  - id phải duy nhất TRONG và GIỮA các nguồn (lỗi -> dừng);
  - `differential_diagnoses` trỏ tới id không tồn tại -> chỉ cảnh báo (BYT trỏ tới bệnh
    chưa có bài riêng là chuyện bình thường).

Chạy: python data-ingest/01_normalize/scripts/01_normalize_diseases.py [-v]
"""
import json
import sys
from pathlib import Path

INGEST_DIR = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parents[1] / "output" / "diseases"

SOURCES = {
    "byt": INGEST_DIR / "byt" / "output" / "pdf_guideline_2015.json",
    "who": INGEST_DIR / "who" / "output" / "who_skin_diseases.json",
    "medlineplus": INGEST_DIR / "medlineplus" / "output" / "medlineplus_skin_conditions.json",
}

STR_FIELDS = ["id", "name", "english_name", "type", "summary", "course", "medical_review_status"]
LIST_FIELDS = [
    "common_features",
    "suggestive_phrases",
    "typical_locations",
    "risk_factors",
    "differential_diagnoses",
    "red_flags",
    "safe_advice",
]
REQUIRED = ["id", "name", "summary"]
VERBOSE = "-v" in sys.argv


def _clean_list(values: list) -> list[str]:
    seen: list[str] = []
    for v in values:
        v = str(v).strip()
        if v and v not in seen:
            seen.append(v)
    return seen


def normalize_disease(raw: dict, where: str, errors: list[str]) -> dict:
    d = dict(raw)
    for f in STR_FIELDS:
        v = d.get(f, "")
        d[f] = v.strip() if isinstance(v, str) else str(v)
    for f in LIST_FIELDS:
        v = d.get(f, [])
        if not isinstance(v, list):
            errors.append(f"{where}: field `{f}` phải là list, gặp {type(v).__name__}")
            v = []
        d[f] = _clean_list(v)
    for f in REQUIRED:
        if not d[f]:
            errors.append(f"{where}: thiếu field bắt buộc `{f}`")
    d.setdefault("references", [])
    d.setdefault("differential_diagnosis_details", [])
    return d


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    normalized: dict[str, list[dict]] = {}
    id_owner: dict[str, str] = {}

    for source, path in SOURCES.items():
        if not path.exists():
            errors.append(f"{source}: không thấy {path}")
            continue
        items = json.loads(path.read_text(encoding="utf-8"))
        out = []
        for i, raw in enumerate(items):
            d = normalize_disease(raw, f"{source}[{i}] ({raw.get('id', '?')})", errors)
            if d["id"] in id_owner:
                errors.append(f"id trùng: `{d['id']}` ở {source} và {id_owner[d['id']]}")
            id_owner[d["id"]] = source
            out.append(d)
        normalized[source] = out

    for source, items in normalized.items():
        for d in items:
            for ref in d["differential_diagnoses"]:
                if ref not in id_owner:
                    warnings.append(f"{source}/{d['id']}: differential `{ref}` không có bài riêng")

    if VERBOSE:
        for w in warnings:
            print(f"[cảnh báo] {w}")
    if errors:
        for e in errors:
            print(f"[lỗi] {e}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for source, items in normalized.items():
        out_path = OUT_DIR / SOURCES[source].name
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"-> {source:12s} {len(items):3d} bệnh -> {out_path}")
    print(
        f"Tổng {sum(len(v) for v in normalized.values())} bệnh, {len(warnings)} differential "
        "chưa có bài riêng (thêm -v để xem chi tiết)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
