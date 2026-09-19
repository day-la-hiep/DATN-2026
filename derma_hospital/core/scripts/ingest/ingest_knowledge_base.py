"""Ingest guideline da liễu (`knowledge_base/data/chunks/all_chunks.json`, 435 chunk từ
87 bệnh — BYT 75/2015, WHO, MedlinePlus, xem `knowledge_base/README.md`) vào Qdrant, để
`app/agent/tools/knowledge_base_search.py` chỉ cần query lúc runtime, không đọc file
JSON/gọi embedding API mỗi lần agent chạy — cùng nguyên tắc "ingest riêng, tool query
store có sẵn" như `data/PrimeKG`/`data/dermo` (`load_primekg.py`/`load_dermo.py`) ingest
vào Neo4j.

Idempotent + resumable: point id = uuid5 deterministic từ `chunk_id` gốc (vd
"mun_trung_ca_medlineplus::overview"). Trước khi embed 1 batch, script kiểm tra chunk đã
có trong Qdrant chưa (`existing_kb_point_ids`) và bỏ qua — chunk đã ingest không bị embed
lại nếu script dừng giữa chừng rồi chạy lại.

Embedding LOCAL (`app/agent/embeddings.py`, sentence-transformers, không gọi API ngoài)
— KHÔNG còn giới hạn rate limit như bản Google embeddings cũ, chạy 1 lượt liên tục.

Chạy: cd core && python scripts/ingest/ingest_knowledge_base.py [--reset]
`--reset`: xoá sạch collection Qdrant trước khi ingest lại từ đầu (vd đổi embedding
model/dim, hoặc nghi ngờ dữ liệu cũ có rác).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from qdrant_client.models import PointStruct  # noqa: E402

from app.agent.tools.knowledge_base_search import (  # noqa: E402
    KB_EMBEDDING_DIM,
    get_kb_embeddings,
)
from app.infra.qdrant_client import (  # noqa: E402
    delete_kb_collection,
    ensure_kb_collection,
    existing_kb_point_ids,
    upsert_kb_chunks,
)

CHUNKS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge_base"
    / "data"
    / "chunks"
    / "all_chunks.json"
)

_BATCH_SIZE = 50


def _load_chunks() -> list[dict[str, Any]]:
    payload = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    return payload["chunks"]


def _point_id(chunk: dict[str, Any]) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))


def _to_point(chunk: dict[str, Any], vector: list[float]) -> PointStruct:
    return PointStruct(
        id=_point_id(chunk),
        vector=vector,
        payload={
            "chunk_id": chunk["chunk_id"],
            "chunk_type": chunk.get("chunk_type"),
            "disease_id": chunk.get("disease_id"),
            "disease_name": chunk.get("disease_name"),
            "english_name": chunk.get("english_name"),
            "disease_type": chunk.get("disease_type"),
            "text": chunk.get("text"),
            "source_label": chunk.get("source_label"),
            "source_page": chunk.get("source_page"),
            "source_file": chunk.get("source_file"),
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Xoá collection cũ trước khi ingest")
    args = parser.parse_args()

    chunks = _load_chunks()
    print(f"Đã đọc {len(chunks)} chunk từ {CHUNKS_PATH}")

    if args.reset:
        print("Xoá collection Qdrant cũ...")
        await delete_kb_collection()

    await ensure_kb_collection(dim=KB_EMBEDDING_DIM)
    embeddings = get_kb_embeddings()

    done = 0
    for start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[start : start + _BATCH_SIZE]
        ids = [_point_id(c) for c in batch]
        already = await existing_kb_point_ids(ids)
        pending = [c for c, pid in zip(batch, ids) if pid not in already]
        done += len(batch) - len(pending)

        if pending:
            texts = [c["text"] for c in pending]
            vectors = await embeddings.aembed_documents(texts)
            points = [_to_point(c, v) for c, v in zip(pending, vectors)]
            await upsert_kb_chunks(points)
            done += len(pending)

        print(f"  Đã ingest {done}/{len(chunks)} chunk...")

    print("Hoàn tất ingest knowledge base vào Qdrant.")


if __name__ == "__main__":
    asyncio.run(main())
