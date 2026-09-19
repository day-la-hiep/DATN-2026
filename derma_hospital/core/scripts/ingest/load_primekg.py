#!/usr/bin/env python3
"""Nạp knowledge graph da liễu (đã lọc sẵn từ PrimeKG) vào Neo4j — dùng cho tool
`query_dermatology_kg` (`app/agent/tools/knowledge_graph.py`).

Data đã chuyển vào `core/data/primekg/` (từ `../../data/PrimeKG/processed/`, xem
`data/PrimeKG/process_dermatology_kg.py` — pipeline RAW -> processed CSV, dev-only, cần
toàn bộ PrimeKG upstream toolkit ~1GB, KHÔNG deploy) để nằm trong build context của
`core/Dockerfile`, chạy được cả dev lẫn prod (`docker compose exec`) mà không cần mount
gì thêm — chỉ 2 file cần cho việc NẠP (~48MB), không phải toàn bộ pipeline xử lý.

Input: `data/primekg/derma_nodes.csv` (36k dòng, cột id/name/type/source) +
`data/primekg/derma_edges.csv` (474k dòng, cột relation/display_relation/x_id/x_name/
x_type/y_id/y_name/y_type).

Mỗi node có 2 label: `:Entity` (chung, để tra theo `id` lúc nạp cạnh mà không cần biết
type) + 1 label riêng theo `type` (vd `:Disease`, `:GeneProtein`) để Cypher query dễ lọc
theo loại thực thể. Mỗi cạnh có relationship type = `relation` viết hoa (vd
`DISEASE_PHENOTYPE_POSITIVE`), giữ `display_relation` làm property để hiển thị.

Chạy:
  cd core && python scripts/ingest/load_primekg.py [--reset]
`--reset`: xoá sạch `:Entity` (và mọi label con, mọi cạnh) trước khi nạp lại — dùng khi
cần load lại từ đầu (dữ liệu processed đổi, hoặc Neo4j volume mới tinh nghi có rác).
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import settings  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "primekg"
NODES_CSV = DATA_DIR / "derma_nodes.csv"
EDGES_CSV = DATA_DIR / "derma_edges.csv"

BATCH_SIZE = 5000


def to_label(type_str: str) -> str:
    """"gene/protein" -> "GeneProtein", "effect/phenotype" -> "EffectPhenotype"."""
    parts = re.split(r"[^a-zA-Z0-9]+", type_str)
    return "".join(p.capitalize() for p in parts if p)


def to_rel_type(relation: str) -> str:
    """"disease_phenotype_positive" -> "DISEASE_PHENOTYPE_POSITIVE"."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", relation).strip("_").upper()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def batched(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def reset(driver) -> None:
    print("Xoá dữ liệu PrimeKG cũ (:Entity và mọi label/cạnh liên quan)...")
    with driver.session() as session:
        session.run("MATCH (n:Entity) DETACH DELETE n")


def load_nodes(driver, rows: list[dict]) -> None:
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row["type"], []).append(row)

    with driver.session() as session:
        session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")

        for type_str, type_rows in by_type.items():
            # Label ghép thẳng vào chuỗi Cypher (không qua tham số) — an toàn vì
            # `label` tính từ `type_str`, vốn chỉ nhận 1 trong 10 giá trị cố định của
            # `derma_nodes.csv` (không phải input người dùng), không cần APOC.
            label = to_label(type_str)
            query = (
                f"UNWIND $batch AS row "
                f"MERGE (n:Entity:{label} {{id: row.id}}) "
                f"SET n.name = row.name, n.type = row.type, n.source = row.source"
            )
            total = 0
            for batch in batched(type_rows, BATCH_SIZE):
                payload = [
                    {"id": r["id"], "name": r["name"], "type": r["type"], "source": r["source"]}
                    for r in batch
                ]
                session.run(query, batch=payload)
                total += len(batch)
            print(f"  [nodes] {type_str} ({label}): {total}")


def load_edges(driver, rows: list[dict]) -> None:
    by_relation: dict[str, list[dict]] = {}
    for row in rows:
        by_relation.setdefault(row["relation"], []).append(row)

    with driver.session() as session:
        for relation, rel_rows in by_relation.items():
            rel_type = to_rel_type(relation)
            query = (
                f"UNWIND $batch AS row "
                f"MATCH (x:Entity {{id: row.x_id}}), (y:Entity {{id: row.y_id}}) "
                f"MERGE (x)-[r:{rel_type}]->(y) "
                f"SET r.display_relation = row.display_relation"
            )
            total = 0
            for batch in batched(rel_rows, BATCH_SIZE):
                payload = [
                    {"x_id": r["x_id"], "y_id": r["y_id"], "display_relation": r["display_relation"]}
                    for r in batch
                ]
                session.run(query, batch=payload)
                total += len(batch)
            print(f"  [edges] {relation} ({rel_type}): {total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Xoá dữ liệu cũ trước khi nạp")
    args = parser.parse_args()

    print(f"Kết nối Neo4j: {settings.NEO4J_URL}")
    driver = GraphDatabase.driver(
        settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    driver.verify_connectivity()

    if args.reset:
        reset(driver)

    t0 = time.time()
    print("Đọc CSV...")
    nodes = read_csv(NODES_CSV)
    edges = read_csv(EDGES_CSV)
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    print("Nạp nodes...")
    load_nodes(driver, nodes)

    print("Nạp edges...")
    load_edges(driver, edges)

    driver.close()
    print(f"Xong trong {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Lỗi: {exc}", file=sys.stderr)
        sys.exit(1)
