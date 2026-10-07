"""Lưu vào kho tri thức (bước 4) -> Qdrant, không LLM.

Embed `context_text` của từng chunk (đường dẫn mục lục + nội dung) bằng embedding local và nạp vào collection chunk sách
của Qdrant cùng sparse vector BM25 (do `ChunkIndex.upsert_chunks` mã hoá từ cùng văn bản, để agent tìm từ khoá ngay trên Qdrant), kèm metadata part/section/topic/trang và vị trí PDF nguồn trong MinIO. Nạp lại xoá các point cũ của sách trước,
nên chạy lại bước Chia đoạn rồi bước này luôn cho kết quả khớp `chunks.jsonl`. Ghi `index.json` để biết lần nạp gần nhất."""
from datetime import UTC, datetime
from typing import Any

from . import StageContext, StageError

BATCH = 64


def run(ctx: StageContext) -> dict:
    files, vectors = ctx.files, ctx.require_vectors()
    chunks = files.read_jsonl("chunks.jsonl")
    if not chunks:
        raise StageError("Chưa có đoạn nội dung nào — hãy làm bước Chia đoạn trước.")
    document_id = ctx.document_id
    extra: dict[str, Any] = {
        "document_title": ctx.meta().get("title", document_id),
        "source_bucket": files.bucket,
        "source_pdf": files.key("source.pdf"),
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
    vectors.delete_chunks(document_id)  # bỏ các đoạn cũ của tài liệu (đã đổi hoặc không còn)
    for i in range(0, len(chunks), BATCH):
        vectors.upsert_chunks(document_id, chunks[i : i + BATCH], embeddings[i : i + BATCH], extra)
        ctx.progress(len(chunks) + min(i + BATCH, len(chunks)), len(chunks) * 2, "lưu vào Qdrant")
    stored = vectors.count_chunks(document_id)
    if stored != len(chunks):
        raise StageError(f"Số đoạn đã lưu ({stored}) khác số đoạn cần lưu ({len(chunks)}).")
    info = {"collection": vectors.collection, "points": stored, "embedding_model": model, "dimension": dim,
            "indexed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    files.write_json("index.json", info)
    return {"points": stored, "collection": info["collection"], "embedding_model": model, "dimension": dim}
