#!/usr/bin/env python3
"""Nạp KB thuật ngữ DermO (đã trích xuất từ `dermatology.obo`) vào Neo4j — dùng cho tool
`lookup_dermo_term` (`app/agent/tools/dermo_terms.py`).

Data đã chuyển vào `core/data/dermo/` (từ `../../data/dermo/processed/`, xem
`data/dermo/process_dermo_ontology.py` — pipeline RAW .obo -> processed JSON, dev-only,
KHÔNG deploy) để nằm trong build context của `core/Dockerfile`.

Input: `data/dermo/dermo_kg.json` (key `terms`, mỗi term: id/name/def/synonyms/xrefs/
is_a/relationships/alt_ids/is_obsolete — xem `process_dermo_ontology.py`).

Mỗi term -> 1 node `:DermoTerm {id, name, def, synonyms, xrefs, alt_ids, is_obsolete}`.
Label RIÊNG, KHÔNG dùng chung `:Entity` với PrimeKG (`load_primekg.py`) — 2 namespace id
khác nhau (`DERMO:0000000` vs số thuần), tránh lẫn schema khi tool `query_dermatology_kg`
(PrimeKG, `knowledge_graph.py`) tự introspect Neo4j.

Quan hệ:
  - `is_a`            -> `(:DermoTerm)-[:IS_A]->(:DermoTerm cha)`
  - `relationships`    -> type viết hoa (vd `has_symptom` -> `HAS_SYMPTOM`), giữ đúng
    chiều gốc trong OBO (term -[:REL]-> target).

Chạy:
  cd core && python scripts/ingest/load_dermo.py [--reset]
`--reset`: xoá sạch `:DermoTerm` (và mọi cạnh) trước khi nạp lại.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import settings  # noqa: E402

KG_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "dermo" / "dermo_kg.json"

BATCH_SIZE = 1000


def to_rel_type(name: str) -> str:
    """"has_symptom" -> "HAS_SYMPTOM"."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").upper()


def batched(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def reset(driver) -> None:
    print("Xoá dữ liệu DermO cũ (:DermoTerm và mọi cạnh liên quan)...")
    with driver.session() as session:
        session.run("MATCH (n:DermoTerm) DETACH DELETE n")


def load_terms(driver, terms: list[dict]) -> None:
    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT dermo_term_id IF NOT EXISTS "
            "FOR (t:DermoTerm) REQUIRE t.id IS UNIQUE"
        )
        query = (
            "UNWIND $batch AS row "
            "MERGE (t:DermoTerm {id: row.id}) "
            "SET t.name = row.name, t.def = row.def, t.synonyms = row.synonyms, "
            "    t.xrefs = row.xrefs, t.alt_ids = row.alt_ids, "
            "    t.is_obsolete = row.is_obsolete"
        )
        total = 0
        for batch in batched(terms, BATCH_SIZE):
            payload = [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "def": t["def"],
                    "synonyms": t["synonyms"],
                    "xrefs": t["xrefs"],
                    "alt_ids": t["alt_ids"],
                    "is_obsolete": t["is_obsolete"],
                }
                for t in batch
            ]
            session.run(query, batch=payload)
            total += len(batch)
        print(f"  [terms] {total}")


def load_is_a(driver, terms: list[dict]) -> None:
    rows = [
        {"id": t["id"], "parent_id": parent_id}
        for t in terms
        for parent_id in t["is_a"]
    ]
    with driver.session() as session:
        query = (
            "UNWIND $batch AS row "
            "MATCH (t:DermoTerm {id: row.id}), (p:DermoTerm {id: row.parent_id}) "
            "MERGE (t)-[:IS_A]->(p)"
        )
        total = 0
        for batch in batched(rows, BATCH_SIZE):
            session.run(query, batch=batch)
            total += len(batch)
        print(f"  [is_a] {total}")


def load_relationships(driver, terms: list[dict]) -> None:
    by_type: dict[str, list[dict]] = {}
    for t in terms:
        for rel in t["relationships"]:
            rel_type = to_rel_type(rel["type"])
            by_type.setdefault(rel_type, []).append({"id": t["id"], "target_id": rel["target"]})

    with driver.session() as session:
        for rel_type, rows in by_type.items():
            # Label ghép thẳng vào chuỗi Cypher (không qua tham số) — an toàn vì
            # `rel_type` tính từ vocab `relationship:` cố định của DermO (vd
            # `has_symptom`, `results_in`), không phải input người dùng.
            query = (
                "UNWIND $batch AS row "
                "MATCH (t:DermoTerm {id: row.id}), (target:DermoTerm {id: row.target_id}) "
                f"MERGE (t)-[:{rel_type}]->(target)"
            )
            total = 0
            for batch in batched(rows, BATCH_SIZE):
                session.run(query, batch=batch)
                total += len(batch)
            print(f"  [{rel_type}] {total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Xoá dữ liệu cũ trước khi nạp")
    args = parser.parse_args()

    if not KG_JSON.exists():
        print(f"[Lỗi] Không tìm thấy {KG_JSON}.")
        sys.exit(1)

    print(f"Kết nối Neo4j: {settings.NEO4J_URL}")
    driver = GraphDatabase.driver(
        settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    driver.verify_connectivity()

    if args.reset:
        reset(driver)

    t0 = time.time()
    print("Đọc JSON...")
    terms = json.loads(KG_JSON.read_text(encoding="utf-8"))["terms"]
    print(f"  {len(terms)} term")

    print("Nạp terms...")
    load_terms(driver, terms)

    print("Nạp quan hệ is_a...")
    load_is_a(driver, terms)

    print("Nạp quan hệ khác (has_symptom, results_in...)...")
    load_relationships(driver, terms)

    driver.close()
    print(f"Xong trong {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Lỗi: {exc}", file=sys.stderr)
        sys.exit(1)
