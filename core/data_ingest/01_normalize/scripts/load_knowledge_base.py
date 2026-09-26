"""
load_knowledge_base.py
======================
Chia guideline da liễu thành chunk rồi embed + đẩy THẲNG vào Qdrant (collection KB) — không
qua file trung gian. `app/agent/tools/knowledge_base_search.py` chỉ query Qdrant lúc runtime.

Input : ../output/diseases/*.json (BYT + WHO + MedlinePlus, do 01_normalize_diseases.py).
        Nên chạy `04_link_dermo_ids.py` TRƯỚC script này để mỗi bệnh có sẵn `dermo_id`
        (cầu nối id-based với PrimeKG/DermO, xem field `dermo_id` trong
        `disease_to_chunks()` + `app/agent/tools/knowledge_base_search.py`) — không bắt
        buộc, thiếu thì `dermo_id` payload chỉ là null, tool vẫn chạy bình thường.

Mỗi bệnh được chia thành tối đa 5 loại chunk:
  - overview      : tên + tóm tắt + phân loại + diễn tiến: name + english_name + summary + type + course
  - symptoms      : triệu chứng + vị trí + cụm từ đặc trưng: common_features + typical_locations + suggestive_phrases
  - differential  : phân biệt chẩn đoán: differential_diagnosis_details + differential_diagnoses
  - advice        : lời khuyên an toàn: safe_advice
  - risk          : yếu tố nguy cơ + dấu hiệu cảnh báo: risk_factors + red_flags

Idempotent + resumable: point id = uuid5 deterministic từ `chunk_id` (vd
"mun_trung_ca_medlineplus::overview"). Trước khi embed 1 batch, script kiểm tra chunk đã có
trong Qdrant chưa (`existing_kb_point_ids`) và bỏ qua — chunk đã ingest không bị embed lại
nếu script dừng giữa chừng rồi chạy lại. Embedding LOCAL (`app/agent/embeddings.py`,
sentence-transformers), không gọi API ngoài, không rate limit.

Chạy (cần Qdrant đang chạy; trong container: `docker compose exec <core> python ...`):
    cd core && python data-ingest/01_normalize/scripts/load_knowledge_base.py [--reset]
        --reset            xoá sạch collection Qdrant trước khi nạp lại (đổi embedding model/dim,
                           hoặc nghi ngờ dữ liệu cũ có rác)
        --dry-run          chỉ chunk + in báo cáo, không đụng Qdrant/embedding
        --dump-chunks FILE ghi thêm chunk ra JSON (debug, hoặc cho pipeline FAISS cũ ở
                           knowledge_base/scripts/build_index_from_chunks.py)
        --kb DIR           thư mục chứa diseases/ (mặc định ../output)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import uuid
from pathlib import Path
from typing import Any

CORE_DIR = Path(__file__).resolve().parents[3]  # core/ — để import `app.*`
sys.path.insert(0, str(CORE_DIR))

# ---------------------------------------------------------------------------
# Đường dẫn gốc của project
# ---------------------------------------------------------------------------
NORMALIZE_DIR = Path(__file__).resolve().parents[1]  # thư mục normalize (chứa scripts/, output/)
DEFAULT_KB = NORMALIZE_DIR / "output"

_BATCH_SIZE = 50


# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------
CHUNK_TYPES = ("overview", "symptoms", "differential", "advice", "risk")

SOURCE_LABEL = {
    "byt_75_2015": "BYT 75/QĐ-BYT 2015",
}


# ---------------------------------------------------------------------------
# Bước 1: Các hàm tạo text cho từng loại chunk
# ---------------------------------------------------------------------------

def _join(items: list[str], sep: str = ", ") -> str:
    """Nối danh sách thành chuỗi, trả về chuỗi rỗng nếu list trống."""
    return sep.join(items) if items else ""


def _build_overview(d: dict) -> str | None:
    """
    Chunk tổng quan: mô tả chính của bệnh.
    Match tốt khi người dùng hỏi tên bệnh hoặc mô tả chung.

    Ví dụ: "Bệnh chốc là gì?", "Impetigo là bệnh gì?"
    """
    parts = [
        f"Bệnh: {d['name']} ({d.get('english_name', '')}).",
        f"Phân loại: {d.get('type', '')}.",
        d.get("summary", ""),
    ]
    course = d.get("course", "")
    if course:
        parts.append(f"Diễn tiến: {course}")
    return " ".join(p for p in parts if p).strip() or None


def _build_symptoms(d: dict) -> str | None:
    """
    Chunk triệu chứng: đặc điểm lâm sàng chi tiết.
    Match tốt khi người dùng mô tả triệu chứng cụ thể.

    Ví dụ: "bị mụn nước ở kẽ ngón tay ngứa về đêm"
    """
    features = _join(d.get("common_features", []))
    locations = _join(d.get("typical_locations", []))
    phrases = _join(d.get("suggestive_phrases", []))

    parts = []
    if features:
        parts.append(f"Triệu chứng thường gặp của {d['name']}: {features}.")
    if locations:
        parts.append(f"Vị trí tổn thương: {locations}.")
    if phrases:
        parts.append(f"Cụm từ đặc trưng: {phrases}.")
    return " ".join(parts).strip() or None


def _build_differential(d: dict) -> str | None:
    """
    Chunk phân biệt chẩn đoán.
    Match tốt khi người dùng hỏi phân biệt hoặc bệnh trông giống nhau.

    Ví dụ: "làm sao phân biệt chốc với thủy đậu?"
    """
    detail = d.get("differential_diagnosis_details", "").strip()
    dd_ids = _join(d.get("differential_diagnoses", []))
    if not detail and not dd_ids:
        return None
    parts = [f"Phân biệt chẩn đoán của {d['name']}."]
    if dd_ids:
        parts.append(f"Bệnh cần phân biệt: {dd_ids}.")
    if detail:
        parts.append(detail)
    return " ".join(parts).strip()


def _build_advice(d: dict) -> str | None:
    """
    Chunk lời khuyên an toàn.
    Match tốt khi người dùng hỏi điều trị, chăm sóc tại nhà.

    Ví dụ: "bệnh ghẻ cần làm gì tại nhà?"
    """
    advice_list = d.get("safe_advice", [])
    if not advice_list:
        return None
    advice_text = " ".join(advice_list)
    return f"Lời khuyên và chăm sóc cho {d['name']}: {advice_text}".strip()


def _build_risk(d: dict) -> str | None:
    """
    Chunk yếu tố nguy cơ + cảnh báo đỏ.
    Match tốt khi người dùng hỏi nguy cơ hoặc dấu hiệu nguy hiểm.

    Ví dụ: "ai dễ bị viêm nang lông?", "dấu hiệu nguy hiểm của nhọt?"
    """
    risks = _join(d.get("risk_factors", []))
    flags = _join(d.get("red_flags", []))
    if not risks and not flags:
        return None
    parts = [f"Yếu tố nguy cơ và cảnh báo của {d['name']}."]
    if risks:
        parts.append(f"Yếu tố nguy cơ: {risks}.")
    if flags:
        parts.append(f"Dấu hiệu cần cấp cứu / dấu đỏ: {flags}.")
    return " ".join(parts).strip()


# Bảng ánh xạ: loại chunk → hàm tạo text
_BUILDERS: dict[str, Any] = {
    "overview":     _build_overview,
    "symptoms":     _build_symptoms,
    "differential": _build_differential,
    "advice":       _build_advice,
    "risk":         _build_risk,
}


# ---------------------------------------------------------------------------
# Bước 2: Chuyển 1 bệnh → nhiều chunk
# ---------------------------------------------------------------------------

def disease_to_chunks(disease: dict) -> list[dict]:
    """
    Chuyển 1 object bệnh thành danh sách các chunk.

    Mỗi chunk bao gồm:
      - chunk_id        : định danh duy nhất "<disease_id>::<chunk_type>"
      - chunk_type      : loại chunk (overview / symptoms / ...)
      - disease_id      : id bệnh gốc
      - dermo_id        : id DermO ontology (vd "DERMO:0000811") nếu khớp được — gắn bởi
                          `04_link_dermo_ids.py`, cầu nối id-based với
                          `app/agent/tools/entity_grounding.py` (field `dermo.id`); null
                          nếu bệnh này không match được DermO term nào.
      - disease_name    : tên tiếng Việt
      - english_name    : tên tiếng Anh
      - disease_type    : phân loại bệnh (Bệnh da nhiễm khuẩn, ...)
      - text            : văn bản sẽ được embed → vector
      - source_doc      : mã tài liệu nguồn
      - source_label    : nhãn hiển thị của nguồn
      - source_page     : trang trong tài liệu gốc
      - medical_review_status : trạng thái kiểm duyệt y tế
      - disease         : toàn bộ object bệnh (dùng khi render response)
    """
    disease_id = disease.get("id", "unknown")
    ref = disease.get("references", [{}])[0]
    source_doc = ref.get("source_id", "")

    chunks: list[dict] = []
    for chunk_type, builder in _BUILDERS.items():
        text = builder(disease)
        if not text:
            # Bỏ qua chunk nếu không có dữ liệu
            continue
        chunks.append(
            {
                "chunk_id": f"{disease_id}::{chunk_type}",
                "chunk_type": chunk_type,
                "disease_id": disease_id,
                "dermo_id": disease.get("dermo_id"),
                "disease_name": disease.get("name", ""),
                "english_name": disease.get("english_name", ""),
                "disease_type": disease.get("type", ""),
                "source_file": disease.get("_source_file", ""),  # file JSON nguồn
                "text": text,
                "source_doc": source_doc,
                "source_label": SOURCE_LABEL.get(source_doc, source_doc),
                "source_page": ref.get("page_start"),
                "medical_review_status": disease.get(
                    "medical_review_status", "unknown"
                ),
                "disease": disease,  # payload đầy đủ cho LLM render
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Bước 3: Load tất cả bệnh từ thư mục diseases/
# ---------------------------------------------------------------------------

def load_diseases(kb_path: Path) -> list[dict]:
    """Load tất cả bệnh, kèm tên file nguồn để tracking."""
    diseases: list[dict] = []
    for path in sorted((kb_path / "diseases").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            # Gắn tên file nguồn vào mỗi object (dùng khi tạo chunk metadata)
            item["_source_file"] = path.name
        diseases.extend(items)
    return diseases


# ---------------------------------------------------------------------------
# Bước 4: Tạo báo cáo thống kê
# ---------------------------------------------------------------------------

def build_stats(chunks: list[dict], diseases: list[dict]) -> dict:
    type_counts: dict[str, int] = {t: 0 for t in CHUNK_TYPES}
    for chunk in chunks:
        ct = chunk["chunk_type"]
        if ct in type_counts:
            type_counts[ct] += 1

    disease_type_counts: dict[str, int] = {}
    for d in diseases:
        dt = d.get("type", "unknown")
        disease_type_counts[dt] = disease_type_counts.get(dt, 0) + 1

    # Đếm bệnh theo file nguồn
    source_file_counts: dict[str, int] = {}
    for d in diseases:
        sf = d.get("_source_file", "unknown")
        source_file_counts[sf] = source_file_counts.get(sf, 0) + 1

    return {
        "total_diseases": len(diseases),
        "total_chunks": len(chunks),
        "avg_chunks_per_disease": round(len(chunks) / max(len(diseases), 1), 2),
        "chunks_by_type": type_counts,
        "diseases_by_category": disease_type_counts,
        "diseases_by_source_file": source_file_counts,
    }


# ---------------------------------------------------------------------------
# Bước 5: Đẩy vào Qdrant
# ---------------------------------------------------------------------------

def _point_id(chunk: dict[str, Any]) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))


def _to_point(chunk: dict[str, Any], vector: list[float]):
    from qdrant_client.models import PointStruct

    return PointStruct(
        id=_point_id(chunk),
        vector=vector,
        payload={
            "chunk_id": chunk["chunk_id"],
            "chunk_type": chunk.get("chunk_type"),
            "disease_id": chunk.get("disease_id"),
            "dermo_id": chunk.get("dermo_id"),
            "disease_name": chunk.get("disease_name"),
            "english_name": chunk.get("english_name"),
            "disease_type": chunk.get("disease_type"),
            "text": chunk.get("text"),
            "source_label": chunk.get("source_label"),
            "source_page": chunk.get("source_page"),
            "source_file": chunk.get("source_file"),
        },
    )


async def ingest_to_qdrant(chunks: list[dict], reset: bool) -> None:
    # Import muộn để --dry-run chạy được khi chưa cài/không có Qdrant.
    from agent.tools.knowledge_base_search import KB_EMBEDDING_DIM, get_kb_embeddings
    from app.infra.qdrant_client import (
        delete_kb_collection,
        ensure_kb_collection,
        existing_kb_point_ids,
        upsert_kb_chunks,
    )

    if reset:
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
            vectors = await embeddings.aembed_documents([c["text"] for c in pending])
            await upsert_kb_chunks([_to_point(c, v) for c, v in zip(pending, vectors)])
            done += len(pending)

        print(f"  Đã ingest {done}/{len(chunks)} chunk...")

    print("Hoàn tất ingest knowledge base vào Qdrant.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def print_report(stats: dict, skipped: int) -> None:
    print("\n" + "=" * 55)
    print("  KB Chunking — Kết quả")
    print("=" * 55)
    print(f"  Tổng số bệnh         : {stats['total_diseases']}")
    print(f"  Tổng số chunk        : {stats['total_chunks']}")
    print(f"  Trung bình chunk/bệnh: {stats['avg_chunks_per_disease']}")
    print(f"  Bệnh bị bỏ qua       : {skipped}")
    print("\n  Chunks theo loại:")
    for chunk_type, count in stats["chunks_by_type"].items():
        bar = "█" * (count // max(stats["total_chunks"] // 30, 1))
        print(f"    {chunk_type:<14}: {count:>4}  {bar}")
    print("\n  Bệnh theo file nguồn:")
    for src_file, count in sorted(
        stats.get("diseases_by_source_file", {}).items(), key=lambda x: -x[1]
    ):
        print(f"    {src_file:<45}: {count}")
    print("=" * 55 + "\n")


async def main() -> None:
    # Fix UnicodeEncodeError trên terminal Windows dùng code page cũ (cp1252).
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Chunk guideline da liễu và nạp vào Qdrant.")
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB, help="Thư mục chứa diseases/")
    parser.add_argument("--reset", action="store_true", help="Xoá collection cũ trước khi ingest")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ chunk + báo cáo, không ghi Qdrant")
    parser.add_argument("--dump-chunks", type=Path, help="Ghi thêm chunk ra file JSON (debug)")
    args = parser.parse_args()

    kb_dir = args.kb.resolve()
    if not kb_dir.exists():
        print(f"[ERROR] Không tìm thấy thư mục knowledge base: {kb_dir}")
        sys.exit(1)

    diseases = load_diseases(kb_dir)
    print(f"[INFO] Đọc {len(diseases)} bệnh từ {kb_dir}")

    all_chunks: list[dict] = []
    skipped = 0
    for disease in diseases:
        chunks = disease_to_chunks(disease)
        if not chunks:
            skipped += 1
            print(f"[WARN] Bỏ qua bệnh không có chunk: {disease.get('id')}")
        all_chunks.extend(chunks)

    stats = build_stats(all_chunks, diseases)
    print_report(stats, skipped)

    if args.dump_chunks:
        args.dump_chunks.parent.mkdir(parents=True, exist_ok=True)
        args.dump_chunks.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source_kb": "knowledge_base",
                    "source_files": list(stats.get("diseases_by_source_file", {}).keys()),
                    "stats": stats,
                    "chunks": all_chunks,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[INFO] Đã ghi chunk ra {args.dump_chunks}")

    if args.dry_run:
        print("[INFO] --dry-run: không ghi vào Qdrant.")
        return
    await ingest_to_qdrant(all_chunks, reset=args.reset)


if __name__ == "__main__":
    asyncio.run(main())
