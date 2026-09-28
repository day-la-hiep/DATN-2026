#!/usr/bin/env python3
"""Gom các knowledge graph (PrimeKG + DermO) vào 1 chỗ để `core/scripts/ingest/load_*.py`
đọc, kiểm tra header/cấu trúc trước khi nạp Neo4j.

Input : primekg/output/{derma_nodes.csv, derma_edges.csv}
        dermo/output/dermo_kg.json
Output: 01_normalize/output/kg/primekg/{derma_nodes.csv, derma_edges.csv}
        01_normalize/output/kg/dermo/dermo_kg.json

Kiểm tra:
  - CSV đúng header mà `load_primekg.py` mong đợi;
  - mọi `x_id`/`y_id` của cạnh đều có trong nodes (cạnh mồ côi -> lỗi);
  - `dermo_kg.json` có key `terms`, id term duy nhất.

Chạy: python data-ingest/01_normalize/scripts/02_normalize_kg.py
"""
import csv
import json
import shutil
import sys
from pathlib import Path

INGEST_DIR = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parents[1] / "output" / "kg"

NODES_HEADER = ["id", "name", "type", "source"]
EDGES_HEADER = ["relation", "display_relation", "x_id", "x_name", "x_type", "y_id", "y_name", "y_type"]


def check_primekg(nodes_csv: Path, edges_csv: Path) -> list[str]:
    errors: list[str] = []
    with nodes_csv.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        if next(reader) != NODES_HEADER:
            errors.append(f"{nodes_csv.name}: header sai, cần {NODES_HEADER}")
        node_ids = {row[0] for row in reader}
    with edges_csv.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        if next(reader) != EDGES_HEADER:
            errors.append(f"{edges_csv.name}: header sai, cần {EDGES_HEADER}")
        orphans = sum(1 for r in reader if r[2] not in node_ids or r[5] not in node_ids)
    if orphans:
        errors.append(f"{edges_csv.name}: {orphans} cạnh trỏ tới node không có trong nodes.csv")
    return errors


def check_dermo(kg_json: Path) -> list[str]:
    terms = json.loads(kg_json.read_text(encoding="utf-8")).get("terms")
    if terms is None:
        return [f"{kg_json.name}: thiếu key `terms`"]
    ids = [t["id"] for t in terms]
    return [f"{kg_json.name}: id term trùng"] if len(ids) != len(set(ids)) else []


def stage(src: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    print(f"-> {src.relative_to(INGEST_DIR)} -> {(dst_dir / src.name).relative_to(INGEST_DIR)}")


def main() -> int:
    nodes = INGEST_DIR / "primekg" / "output" / "derma_nodes.csv"
    edges = INGEST_DIR / "primekg" / "output" / "derma_edges.csv"
    dermo = INGEST_DIR / "dermo" / "output" / "dermo_kg.json"

    missing = [p for p in (nodes, edges, dermo) if not p.exists()]
    if missing:
        print("\n".join(f"[lỗi] không thấy {p}" for p in missing))
        return 1

    errors = check_primekg(nodes, edges) + check_dermo(dermo)
    if errors:
        print("\n".join(f"[lỗi] {e}" for e in errors))
        return 1

    for src in (nodes, edges):
        stage(src, OUT_DIR / "primekg")
    stage(dermo, OUT_DIR / "dermo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
