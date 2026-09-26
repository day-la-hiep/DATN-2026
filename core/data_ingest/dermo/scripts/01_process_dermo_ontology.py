#!/usr/bin/env python3
"""
Trích xuất DermO (Dermatology Ontology, OBO format) thành KB map thuật ngữ.
==========================================================================
File: data-ingest/dermo/scripts/01_process_dermo_ontology.py

Mục đích:
  Parse `dermatology.obo` (3.427 term, format OBO 1.2) thành:
  1. `dermo_terms.csv`     — bảng đầy đủ mỗi term (id/name/def/synonym/xref/is_a...).
  2. `dermo_term_map.json` — dict phẳng "thuật ngữ (lowercase) -> DERMO id", gộp cả
     `name` lẫn mọi `synonym` của term đó làm key, dùng để CHUẨN HOÁ thuật ngữ da liễu
     (vd người dùng gõ "harlequin baby" -> tra ra DERMO id của "ichthyosis simplex").
  3. `dermo_kg.json`       — gộp toàn bộ term + quan hệ `is_a`/`relationship`
     (vd `has_symptom`) dạng cây, tiện xem/debug hoặc nạp Neo4j sau này.

Term obsolete (`is_obsolete: true`) bị loại khỏi `dermo_term_map.json` (không nên map
thuật ngữ mới vào 1 khái niệm đã lỗi thời) nhưng vẫn giữ trong `dermo_terms.csv` để đối
chiếu khi cần.

Input : dermo/input/dermatology.obo
Output: dermo/output/{dermo_terms.csv, dermo_term_map.json, dermo_kg.json}

Chạy:
  python data-ingest/dermo/scripts/01_process_dermo_ontology.py

Sau đó `01_normalize/` gom `dermo_kg.json` vào `01_normalize/output/kg/` và
`core/data-ingest/01_normalize/scripts/load_dermo.py` nạp Neo4j từ đó.
"""
import csv
import json
import os
import re
import sys

SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # data-ingest/dermo
OBO_PATH = os.path.join(SOURCE_DIR, "input", "dermatology.obo")
OUT_DIR = os.path.join(SOURCE_DIR, "output")

OUT_TERMS_CSV = os.path.join(OUT_DIR, "dermo_terms.csv")
OUT_TERM_MAP_JSON = os.path.join(OUT_DIR, "dermo_term_map.json")
OUT_KG_JSON = os.path.join(OUT_DIR, "dermo_kg.json")

# "id: DERMO:0000001" -> DERMO:0000001 ; "is_a: DERMO:0000000 ! disease" -> lấy phần
# trước " ! " (OBO dùng " ! <name>" làm chú thích người đọc, không phải dữ liệu).
ID_RE = re.compile(r"^(DERMO:\d+)")
SYNONYM_RE = re.compile(r'^"(.*)"\s+(EXACT|RELATED|BROAD|NARROW)\b')
DEF_RE = re.compile(r'^"(.*)"')
RELATIONSHIP_RE = re.compile(r"^(\S+)\s+(DERMO:\d+)")


def strip_trailing_comment(line: str) -> str:
    """OBO cho phép comment cuối dòng dạng ` ! text` (không phải trong dấu ngoặc kép) —
    bỏ đi vì chỉ là annotation người đọc, giữ nguyên phần dữ liệu trước đó."""
    if " ! " in line:
        return line.split(" ! ", 1)[0].strip()
    return line.strip()


def parse_terms(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"[Lỗi] Không tìm thấy file: {path}")
        sys.exit(1)

    terms: list[dict] = []
    current: dict | None = None

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            if line == "[Term]":
                current = {
                    "id": "",
                    "name": "",
                    "def": "",
                    "synonyms": [],
                    "xrefs": [],
                    "is_a": [],
                    "relationships": [],
                    "alt_ids": [],
                    "is_obsolete": False,
                }
                terms.append(current)
                continue

            if current is None or not line.strip() or ":" not in line:
                continue

            tag, _, value = line.partition(":")
            value = value.strip()

            if tag == "id":
                current["id"] = value
            elif tag == "name":
                current["name"] = value
            elif tag == "def":
                m = DEF_RE.match(strip_trailing_comment(value))
                if m:
                    current["def"] = m.group(1)
            elif tag == "synonym":
                m = SYNONYM_RE.match(value)
                if m:
                    current["synonyms"].append(m.group(1))
            elif tag == "xref":
                current["xrefs"].append(strip_trailing_comment(value))
            elif tag == "is_a":
                m = ID_RE.match(value)
                if m:
                    current["is_a"].append(m.group(1))
            elif tag == "alt_id":
                m = ID_RE.match(value)
                if m:
                    current["alt_ids"].append(m.group(1))
            elif tag == "relationship":
                m = RELATIONSHIP_RE.match(value)
                if m:
                    current["relationships"].append({"type": m.group(1), "target": m.group(2)})
            elif tag == "is_obsolete":
                current["is_obsolete"] = value.strip().lower() == "true"

    return [t for t in terms if t["id"]]


def build_term_map(terms: list[dict]) -> dict[str, str]:
    """"thuật ngữ (lowercase) -> DERMO id" — gộp `name` + mọi `synonym`. Term trùng
    thuật ngữ giữa nhiều id (hiếm nhưng có) thì giữ id xuất hiện TRƯỚC trong file (thường
    là id gốc, xrefs đầy đủ hơn) — không ghi đè."""
    term_map: dict[str, str] = {}
    for term in terms:
        if term["is_obsolete"]:
            continue
        labels = [term["name"], *term["synonyms"]]
        for label in labels:
            key = label.strip().lower()
            if key and key not in term_map:
                term_map[key] = term["id"]
    return term_map


def save_outputs(terms: list[dict], term_map: dict[str, str]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(OUT_TERMS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "name", "def", "synonyms", "xrefs", "is_a", "alt_ids", "is_obsolete"]
        )
        for term in terms:
            writer.writerow(
                [
                    term["id"],
                    term["name"],
                    term["def"],
                    "|".join(term["synonyms"]),
                    "|".join(term["xrefs"]),
                    "|".join(term["is_a"]),
                    "|".join(term["alt_ids"]),
                    term["is_obsolete"],
                ]
            )

    with open(OUT_TERM_MAP_JSON, "w", encoding="utf-8") as f:
        json.dump(term_map, f, ensure_ascii=False, indent=2, sort_keys=True)

    kg_json = {
        "metadata": {
            "total_terms": len(terms),
            "total_obsolete": sum(1 for t in terms if t["is_obsolete"]),
            "total_term_map_entries": len(term_map),
        },
        "terms": terms,
    }
    with open(OUT_KG_JSON, "w", encoding="utf-8") as f:
        json.dump(kg_json, f, ensure_ascii=False, indent=2)

    print(f"-> Đã ghi file Terms   : {OUT_TERMS_CSV} ({len(terms)} term)")
    print(f"-> Đã ghi file Term map: {OUT_TERM_MAP_JSON} ({len(term_map)} thuật ngữ)")
    print(f"-> Đã ghi file KG      : {OUT_KG_JSON}")


def main() -> None:
    print("=" * 75)
    print(" Trích xuất DermO Ontology -> KB map thuật ngữ da liễu")
    print("=" * 75)

    terms = parse_terms(OBO_PATH)
    print(f"-> Đã parse {len(terms)} term từ {OBO_PATH}")

    term_map = build_term_map(terms)
    save_outputs(terms, term_map)

    print("=" * 75)
    print(" HOÀN THÀNH")
    print("=" * 75)


if __name__ == "__main__":
    main()
