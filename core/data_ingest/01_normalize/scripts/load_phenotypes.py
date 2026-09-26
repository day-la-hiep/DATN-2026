#!/usr/bin/env python3
"""Nạp phenotype PrimeKG (nút `effect/phenotype` đã có trong Neo4j) vào Qdrant để
`describe_morphology` (`agent/tools/differential.py`) map mô tả tự do -> nút phenotype bằng
semantic search.

Chỉ nạp phenotype có ÍT NHẤT 1 cạnh DISEASE_PHENOTYPE_POSITIVE/NEGATIVE (phenotype không nối
bệnh nào vô dụng cho chẩn đoán phân biệt). Văn bản embed = tên + từ đồng nghĩa DermO nếu tên
khớp chính xác 1 DermO term. Payload `primekg_id` khớp thuộc tính `id` của nút `:Entity`.

Chạy:
  cd core && uv run python data-ingest/01_normalize/scripts/load_phenotypes.py [--reset]
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from neo4j import GraphDatabase
from qdrant_client.models import PointStruct

CORE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE_DIR))

from agent.embeddings import EMBEDDING_DIM, LocalEmbeddings  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.infra.qdrant_client import (  # noqa: E402
    delete_phenotype_collection,
    ensure_phenotype_collection,
    upsert_phenotypes,
)

_QUERY = """
MATCH (p:Entity {type: 'effect/phenotype'})
WHERE EXISTS { (p)-[:DISEASE_PHENOTYPE_POSITIVE|DISEASE_PHENOTYPE_NEGATIVE]-() }
OPTIONAL MATCH (t:DermoTerm)
  WHERE NOT t.is_obsolete AND toLower(t.name) = toLower(p.name)
RETURN p.id AS id, p.name AS name, collect(DISTINCT t.synonyms) AS syns
"""


def _fetch() -> list[dict]:
    driver = GraphDatabase.driver(
        settings.NEO4J_URL, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        rows = [r.data() for r in session.run(_QUERY)]
    driver.close()
    out: dict[str, dict] = {}
    for r in rows:
        synonyms = sorted({s for group in r["syns"] if group for s in group})
        out[r["id"]] = {"id": r["id"], "name": r["name"], "synonyms": synonyms}
    return list(out.values())


async def main(reset: bool) -> None:
    phenotypes = _fetch()
    print(f"Phenotype nối bệnh: {len(phenotypes)}")
    if reset:
        await delete_phenotype_collection()
    await ensure_phenotype_collection(EMBEDDING_DIM)
    texts = [
        p["name"] + (". " + "; ".join(p["synonyms"]) if p["synonyms"] else "")
        for p in phenotypes
    ]
    vectors = LocalEmbeddings().embed_documents(texts)
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"primekg-phenotype:{p['id']}")),
            vector=v,
            payload={"primekg_id": p["id"], "name": p["name"], "synonyms": p["synonyms"]},
        )
        for p, v in zip(phenotypes, vectors)
    ]
    for i in range(0, len(points), 200):
        await upsert_phenotypes(points[i : i + 200])
    print(f"Đã nạp {len(points)} phenotype vào '{settings.QDRANT_PHENOTYPE_COLLECTION}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    asyncio.run(main(parser.parse_args().reset))
