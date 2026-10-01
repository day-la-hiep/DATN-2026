"""Lưu vào kho tri thức (bước 4) -> Qdrant, không LLM.

Embed `context_text` của từng chunk (đường dẫn mục lục + nội dung) bằng embedding local và nạp vào collection chunk sách
của Qdrant, kèm metadata part/section/topic/trang và vị trí PDF nguồn trong MinIO. Nạp lại xoá các point cũ của sách trước,
nên chạy lại bước Chia đoạn rồi bước này luôn cho kết quả khớp `chunks.jsonl`. Ghi `index.json` để biết lần nạp gần nhất."""
from datetime import UTC, datetime
from typing import Any

from . import StageContext, StageError

BATCH = 64


def run(ctx: StageContext) -> dict:
    store, vectors = ctx.store, ctx.require_vectors()
    chunks = store.files.read_jsonl("chunks.jsonl")
    if not chunks:
        raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
    meta = store.meta()
    extra: dict[str, Any] = {
        "book_title": meta.get("title", store.book_id),
        "source_bucket": store.files.bucket,
        "source_pdf": store.files.key("source.pdf"),
    }
    ctx.progress(0, len(chunks), "chuẩn bị kho tri thức")
    embeddings: list[list[float]] = []
    dim, model = 0, ""
    for i in range(0, len(chunks), BATCH):
        part = chunks[i : i + BATCH]
        vecs, dim, model = ctx.require_embedding().embed([c["context_text"] for c in part])
        embeddings += vecs
        ctx.progress(i + len(part), len(chunks) * 2, "tạo vector cho đoạn nội dung")
    vectors.ensure_collection(dim)
    vectors.delete_chunks(store.book_id)  # bỏ các đoạn cũ của sách (đã đổi hoặc không còn)
    for i in range(0, len(chunks), BATCH):
        vectors.upsert_chunks(store.book_id, chunks[i : i + BATCH], embeddings[i : i + BATCH], extra)
        ctx.progress(len(chunks) + min(i + BATCH, len(chunks)), len(chunks) * 2, "lưu vào Qdrant")
    stored = vectors.count_chunks(store.book_id)
    if stored != len(chunks):
        raise StageError(f"Số đoạn đã lưu ({stored}) khác số đoạn cần lưu ({len(chunks)}).")
    info = {"collection": vectors.collection, "points": stored, "embedding_model": model, "dimension": dim,
            "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    store.files.write_json("index.json", info)
    return {"points": stored, "collection": info["collection"], "embedding_model": model, "dimension": dim}
