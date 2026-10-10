#!/usr/bin/env python3
"""
03_build_chunks.py
==================
Tạo các vector chunks từ dữ liệu bệnh lý ĐHYD TP.HCM (dhyd_diseases.json)
theo cùng định dạng chunk của guideline KB cũ (loader `load_knowledge_base.py` đã bỏ; script này chưa có nơi nạp).

Mỗi bệnh lý được chia thành tối đa 5 loại chunk:
  1. overview     : Tên + tên tiếng Anh + tóm tắt + phân loại + diễn tiến
  2. symptoms     : Triệu chứng thường gặp + vị trí tổn thương + cụm từ đặc trưng
  3. differential : Phân biệt chẩn đoán + bệnh cần phân biệt
  4. advice       : Lời khuyên an toàn, hướng dẫn chăm sóc/điều trị tại nhà
  5. risk         : Yếu tố nguy cơ + dấu hiệu cảnh báo đỏ (red flags)

Input : core/data_ingest/dhyd/output/dhyd_diseases.json
Output: core/data_ingest/dhyd/output/dhyd_chunks.json
"""

import io
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# Đảm bảo in tiếng Việt trên console Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
IN_PATH = BASE_DIR / "output" / "dhyd_diseases.json"
OUT_PATH = BASE_DIR / "output" / "dhyd_chunks.json"

CHUNK_TYPES = ("overview", "symptoms", "differential", "advice", "risk")
SOURCE_LABEL = "ĐHYD TP.HCM - Bệnh da liễu thường gặp (2020)"


def _join(items: list[str], sep: str = ", ") -> str:
    return sep.join(items) if items else ""


def _build_overview(d: dict) -> str | None:
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
    advice_list = d.get("safe_advice", [])
    if not advice_list:
        return None
    advice_text = " ".join(advice_list)
    return f"Lời khuyên và chăm sóc cho {d['name']}: {advice_text}".strip()


def _build_risk(d: dict) -> str | None:
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


_BUILDERS: dict[str, Any] = {
    "overview": _build_overview,
    "symptoms": _build_symptoms,
    "differential": _build_differential,
    "advice": _build_advice,
    "risk": _build_risk,
}


def disease_to_chunks(disease: dict) -> list[dict]:
    disease_id = disease.get("id", "unknown")
    ref = disease.get("references", [{}])[0]
    source_doc = ref.get("source_id", "dhyd_2020")

    chunks: list[dict] = []
    for chunk_type, builder in _BUILDERS.items():
        text = builder(disease)
        if not text:
            continue
        chunk_id = f"{disease_id}::{chunk_type}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "point_id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)),
                "chunk_type": chunk_type,
                "disease_id": disease_id,
                "dermo_id": disease.get("dermo_id"),
                "disease_name": disease.get("name", ""),
                "english_name": disease.get("english_name", ""),
                "disease_type": disease.get("type", ""),
                "source_file": "dhyd_diseases.json",
                "text": text,
                "source_doc": source_doc,
                "source_label": SOURCE_LABEL,
                "source_page": ref.get("page_start"),
                "medical_review_status": disease.get("medical_review_status", "verified"),
                "disease": disease,
            }
        )
    return chunks


def main() -> int:
    if not IN_PATH.exists():
        print(f"[LỖI] Không tìm thấy file: {IN_PATH}")
        return 1

    diseases = json.loads(IN_PATH.read_text(encoding="utf-8"))
    print(f"Đang đọc {len(diseases)} bệnh từ {IN_PATH.name}...")

    all_chunks = []
    for d in diseases:
        chunks = disease_to_chunks(d)
        all_chunks.extend(chunks)

    stats: dict[str, int] = {t: 0 for t in CHUNK_TYPES}
    for c in all_chunks:
        stats[c["chunk_type"]] += 1

    payload = {
        "source": "dhyd_2020",
        "label": SOURCE_LABEL,
        "total_diseases": len(diseases),
        "total_chunks": len(all_chunks),
        "avg_chunks_per_disease": round(len(all_chunks) / max(len(diseases), 1), 2),
        "chunks_by_type": stats,
        "chunks": all_chunks,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=======================================================")
    print(f"  Tạo Chunk thành công cho ĐHYD TP.HCM")
    print(f"=======================================================")
    print(f"  Tổng số bệnh lý : {len(diseases)}")
    print(f"  Tổng số chunk   : {len(all_chunks)}")
    print(f"  File output     : {OUT_PATH}")
    print(f"  Phân bố loại chunk:")
    for ct, count in stats.items():
        bar = "█" * (count // 3)
        print(f"    {ct:<14}: {count:>3}  {bar}")
    print(f"=======================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
