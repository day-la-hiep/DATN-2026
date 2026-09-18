"""
build_index_from_chunks.py
==========================
Đọc all_chunks.json (hoặc bất kỳ file chunks nào theo schema),
embed mỗi chunk["text"] bằng sentence-transformers,
lưu vào FAISS IndexFlatIP.

Workflow:
    1. python scripts/build_chunks_kb2.py          ← tạo chunks từ tất cả KB
    2. python scripts/build_index_from_chunks.py   ← tạo FAISS index  ← FILE NÀY

Chạy:
    python scripts/build_index_from_chunks.py
    python scripts/build_index_from_chunks.py --chunks data/chunks/all_chunks.json \\
                                               --output data/semantic_index
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_chunks(chunks_file: Path) -> list[dict]:
    payload = json.loads(chunks_file.read_text(encoding="utf-8"))
    # Hỗ trợ cả 2 schema:
    #   - {"chunks": [...], "stats": {...}}  ← build_chunks_kb2.py output
    #   - [...]                              ← list thuần
    if isinstance(payload, list):
        return payload
    return payload.get("chunks", [])


def get_or_download_model(model_dir: Path) -> "SentenceTransformer":  # type: ignore[name-defined]
    from sentence_transformers import SentenceTransformer  # type: ignore[import]

    if model_dir.exists() and any(model_dir.iterdir()):
        print(f"  Dùng model cache: {model_dir}")
        return SentenceTransformer(
            str(model_dir),
            local_files_only=True,
            tokenizer_kwargs={"fix_mistral_regex": True},
        )
    print(f"  Tải model từ HuggingFace: {MODEL_NAME}")
    model = SentenceTransformer(
        MODEL_NAME,
        tokenizer_kwargs={"fix_mistral_regex": True},
    )
    model.save(str(model_dir))
    print(f"  Model đã lưu tại: {model_dir}")
    return model


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------

def build_index(
    chunks: list[dict],
    model,  # SentenceTransformer
    output_dir: Path,
    batch_size: int = 64,
) -> None:
    import faiss  # type: ignore[import]
    import numpy as np  # type: ignore[import]

    texts = [c["text"] for c in chunks]
    print(f"  Encoding {len(texts)} chunks (batch={batch_size})...")

    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=True,
    )
    vectors = np.asarray(vectors, dtype="float32")

    dim = vectors.shape[1]
    print(f"  Vector shape: {vectors.shape}  (dim={dim})")

    # IndexFlatIP = Inner Product (= cosine khi đã normalize)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    print(f"  FAISS index: {index.ntotal} vectors")

    # Ghi file
    output_dir.mkdir(parents=True, exist_ok=True)
    faiss_path = output_dir / "conditions.faiss"
    meta_path = output_dir / "chunks.json"

    faiss.write_index(index, str(faiss_path))
    meta_path.write_text(
        json.dumps(
            {
                "model_path": "../embedding_model",
                "schema_version": "2.0",
                "total_chunks": len(chunks),
                "dim": dim,
                "chunks": chunks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  ✓ FAISS index lưu tại : {faiss_path}  ({faiss_path.stat().st_size // 1024} KB)")
    print(f"  ✓ Metadata lưu tại   : {meta_path}  ({meta_path.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------------
# Validation: thử search vài query mẫu
# ---------------------------------------------------------------------------

def quick_validate(output_dir: Path, model) -> None:
    import faiss
    import numpy as np

    index = faiss.read_index(str(output_dir / "conditions.faiss"))
    meta = json.loads((output_dir / "chunks.json").read_text(encoding="utf-8"))
    chunks = meta["chunks"]

    test_queries = [
        ("ngứa về đêm kẽ ngón tay", "benh_ghe"),
        ("vảy bạc trên da đầu gối", "vay_nen"),
        ("mảng đỏ mặt mất cảm giác", "benh_phong"),
        ("bọng nước vảy mật ong ở mặt trẻ em", "benh_choc"),
    ]

    print("\n  Validation — top-3 cho mỗi query mẫu:")
    for query, expected_hint in test_queries:
        vec = model.encode([query], normalize_embeddings=True)
        scores, idxs = index.search(np.asarray(vec, dtype="float32"), 3)
        hits = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            c = chunks[idx]
            hits.append(f"{c['disease_id']}::{c['chunk_type']} ({score:.3f})")
        hit_str = "  |  ".join(hits)
        mark = "✓" if any(expected_hint in h for h in hits) else "?"
        print(f"  {mark} [{query[:30]:<30}] → {hit_str}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Embed chunks va build FAISS index."
    )
    parser.add_argument(
        "--chunks",
        default="data/chunks/all_chunks.json",
        help="File chunks JSON (default: data/chunks/all_chunks.json)",
    )
    parser.add_argument(
        "--output",
        default="data/semantic_index",
        help="Thu muc output index (default: data/semantic_index)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size khi encode (default: 64)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Chay validation sau khi build (default: True)",
    )
    args = parser.parse_args()

    chunks_file = Path(args.chunks)
    if not chunks_file.is_absolute():
        chunks_file = ROOT / chunks_file
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    model_dir = ROOT / "data" / "embedding_model"

    print(f"\n{'='*60}")
    print("  Build Semantic Index từ Chunks")
    print(f"{'='*60}")
    print(f"  Chunks file : {chunks_file}")
    print(f"  Output dir  : {output_dir}")
    print(f"  Model dir   : {model_dir}")
    print(f"{'='*60}\n")

    # Load chunks
    if not chunks_file.exists():
        print(f"[ERROR] Không tìm thấy file chunks: {chunks_file}")
        print("  Hãy chạy: python scripts/build_chunks_kb2.py trước")
        sys.exit(1)

    print("[1/3] Load chunks...")
    chunks = load_chunks(chunks_file)
    print(f"  Tổng chunks: {len(chunks)}")

    # Thống kê theo chunk_type
    type_counts: dict[str, int] = {}
    for c in chunks:
        ct = c.get("chunk_type", "unknown")
        type_counts[ct] = type_counts.get(ct, 0) + 1
    for ct, cnt in sorted(type_counts.items()):
        print(f"    {ct:<14}: {cnt}")

    print()
    print("[2/3] Load embedding model...")
    model = get_or_download_model(model_dir)

    print()
    print("[3/3] Build FAISS index...")
    build_index(chunks, model, output_dir, batch_size=args.batch_size)

    if args.validate:
        print()
        print("[Validate] Kiểm tra search nhanh...")
        quick_validate(output_dir, model)

    print(f"\n{'='*60}")
    print("  ✅ Index build hoàn tất!")
    print(f"  Trỏ SemanticRetriever tới: {output_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
