"""
build_chunks_kb2.py
===================
Tạo file all_chunks.json từ knowledge_base/diseases/ (tất cả KB đã gộp).

Mỗi bệnh được chia thành tối đa 5 loại chunk:
  - overview      : tên + tóm tắt + phân loại + diễn tiến: name + english_name + summary + type + course
  - symptoms      : triệu chứng + vị trí + cụm từ đặc trưng: common_features + typical_locations + suggestive_phrases
  - differential  : phân biệt chẩn đoán: differential_diagnosis_details + differential_diagnoses
  - advice        : lời khuyên an toàn: safe_advice
  - risk          : yếu tố nguy cơ + dấu hiệu cảnh báo: risk_factors + red_flags

Output: data/chunks/all_chunks.json

Chạy:
    python scripts/build_chunks_kb2.py
    python scripts/build_chunks_kb2.py --kb knowledge_base --out data/chunks/all_chunks.json
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Đường dẫn gốc của project
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))


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
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Fix UnicodeEncodeError trên terminal Windows dùng code page cũ (cp1252).
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Tao chunks tu knowledge base de indexing vao Vector DB."
    )
    parser.add_argument(
        "--kb",
        default="knowledge_base",
        help="Thư mục knowledge base (default: knowledge_base)",
    )
    parser.add_argument(
        "--out",
        default="data/chunks/all_chunks.json",
        help="Đường dẫn file output (default: data/chunks/all_chunks.json)",
    )
    args = parser.parse_args()

    # Resolve paths
    kb_dir = Path(args.kb)
    if not kb_dir.is_absolute():
        kb_dir = ROOT / kb_dir

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    if not kb_dir.exists():
        print(f"[ERROR] Không tìm thấy thư mục knowledge base: {kb_dir}")
        sys.exit(1)

    print(f"[INFO] Đọc dữ liệu từ: {kb_dir}")
    diseases = load_diseases(kb_dir)
    print(f"[INFO] Tìm thấy {len(diseases)} bệnh.")

    # Tạo chunks
    all_chunks: list[dict] = []
    skipped = 0
    for disease in diseases:
        chunks = disease_to_chunks(disease)
        if not chunks:
            skipped += 1
            print(f"[WARN] Bỏ qua bệnh không có chunk: {disease.get('id')}")
        all_chunks.extend(chunks)

    stats = build_stats(all_chunks, diseases)

    # Ghi output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "source_kb": str(kb_dir.name),
        "source_files": list(stats.get("diseases_by_source_file", {}).keys()),
        "stats": stats,
        "chunks": all_chunks,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # In báo cáo
    print("\n" + "=" * 55)
    print("  KB Chunking — Kết quả")
    print("=" * 55)
    print(f"  Tổng số bệnh         : {stats['total_diseases']}")
    print(f"  Tổng số chunk        : {stats['total_chunks']}")
    print(f"  Trung bình chunk/bệnh: {stats['avg_chunks_per_disease']}")
    print(f"  Bệnh bị bỏ qua       : {skipped}")
    print()
    print("  Chunks theo loại:")
    for chunk_type, count in stats["chunks_by_type"].items():
        bar = "█" * (count // max(stats["total_chunks"] // 30, 1))
        print(f"    {chunk_type:<14}: {count:>4}  {bar}")
    print()
    print("  Bệnh theo file nguồn:")
    for src_file, count in sorted(
        stats.get("diseases_by_source_file", {}).items(), key=lambda x: -x[1]
    ):
        print(f"    {src_file:<45}: {count}")
    print()
    print("  Bệnh theo phân loại:")
    for category, count in sorted(
        stats["diseases_by_category"].items(), key=lambda x: -x[1]
    ):
        print(f"    {category:<40}: {count}")
    print()
    print(f"  Output đã lưu tại: {out_path}")
    print("=" * 55)


if __name__ == "__main__":
    main()
