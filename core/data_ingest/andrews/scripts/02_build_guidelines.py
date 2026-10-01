#!/usr/bin/env python3
"""02_build_guidelines.py - Giai đoạn 2: Trích xuất nội dung từ PDF Andrews sang JSON chuẩn.

Input : 
  - andrews/output/andrews_toc.json (Mục lục từ Giai đoạn 1)
  - Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf (PDF gốc)
  - byt/output/pdf_guideline_2015.json (Danh sách bệnh mốc để đối chiếu và lấy tên tiếng Việt)
Output: 
  - andrews/output/andrews_diseases.json (File guideline theo schema chuẩn của hệ thống)
"""
import io
import json
import os
import re
import sys
from pathlib import Path
from pypdf import PdfReader

# Fix Unicode stdout trên Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
ANDREWS_DIR = SCRIPT_DIR.parent
INGEST_DIR = ANDREWS_DIR.parent
CORE_DIR = INGEST_DIR.parent
REPO_ROOT = CORE_DIR.parent

CANDIDATE_PDFS = [
    REPO_ROOT / "Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf",
    ANDREWS_DIR / "input" / "Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf",
]
PDF_PATH = next((p for p in CANDIDATE_PDFS if p.exists()), None)
TOC_PATH = ANDREWS_DIR / "output" / "andrews_toc.json"
BYT_PATH = INGEST_DIR / "byt" / "output" / "pdf_guideline_2015.json"
OUT_PATH = ANDREWS_DIR / "output" / "andrews_diseases.json"


def clean_text(text: str) -> str:
    """Loại bỏ ký tự lạ, nối dòng bị đứt (dehyphenation)."""
    # Thay thế ngắt dòng gạch nối (vd: pilose - \n baceous -> pilosebaceous)
    text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
    # Gộp các khoảng trắng liên tiếp
    text = re.sub(r"[ \t]+", " ", text)
    # Loại bỏ các dòng chú thích trang / header lặp lại
    text = re.sub(r"Bonus\s+images.*?\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"expertconsult\.inkling\.com", "", text, flags=re.IGNORECASE)
    return text.strip()


def extract_pages_text(reader: PdfReader, start_page: int, end_page: int, max_pages: int = 5) -> str:
    """Trích xuất text từ start_page đến min(end_page, start_page + max_pages)."""
    text_parts = []
    end = min(end_page, start_page + max_pages)
    for p in range(start_page - 1, end):
        if p < len(reader.pages):
            page_text = reader.pages[p].extract_text() or ""
            text_parts.append(page_text)
    return clean_text("\n\n".join(text_parts))


def parse_disease_sections(raw_text: str) -> dict:
    """Tách các phân đoạn chính trong bài viết y khoa của Andrews."""
    # Tìm kiếm các tiêu đề phổ biến trong Andrews
    sections = {
        "summary": "",
        "clinical_features": "",
        "differential": "",
        "complications": "",
        "treatment": "",
    }

    # Bóc đoạn đầu làm summary
    paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    if paras:
        sections["summary"] = paras[0][:500]

    # Tìm phần Clinical features
    cf_match = re.search(r"(?:Clinical\s+features|Signs\s+and\s+symptoms)(.*?)(?:Etiology|Pathology|Differential|Treatment|Complications|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if cf_match:
        sections["clinical_features"] = cf_match.group(1).strip()[:1200]

    # Tìm phần Differential diagnosis
    dd_match = re.search(r"(?:Differential\s+diagnosis|Differential)(.*?)(?:Pathology|Treatment|Complications|Prognosis|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if dd_match:
        sections["differential"] = dd_match.group(1).strip()[:1000]

    # Tìm phần Complications / Prognosis
    comp_match = re.search(r"(?:Complications|Prognosis)(.*?)(?:Treatment|References|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if comp_match:
        sections["complications"] = comp_match.group(1).strip()[:800]

    # Tìm phần Treatment / Management
    tr_match = re.search(r"(?:Treatment|Management)(.*?)(?:References|Complications|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
    if tr_match:
        sections["treatment"] = tr_match.group(1).strip()[:1000]

    return sections


def build_disease_record(
    disease_id: str,
    vi_name: str,
    en_name: str,
    chapter_title: str,
    start_page: int,
    raw_text: str,
    byt_reference: dict | None = None
) -> dict:
    """Tạo bản ghi JSON hoàn chỉnh theo đúng schema chuẩn DATN."""
    sections = parse_disease_sections(raw_text)

    # Lấy thông tin đối chiếu từ BYT nếu có
    common_features = []
    suggestive_phrases = []
    typical_locations = []
    red_flags = []
    safe_advice = []
    differential_diagnoses = []

    if byt_reference:
        common_features = byt_reference.get("common_features", [])
        suggestive_phrases = byt_reference.get("suggestive_phrases", [])
        typical_locations = byt_reference.get("typical_locations", [])
        red_flags = byt_reference.get("red_flags", [])
        safe_advice = byt_reference.get("safe_advice", [])
        differential_diagnoses = byt_reference.get("differential_diagnoses", [])

    # Nếu chưa có từ BYT, trích xuất sơ bộ từ text của Andrews
    summary_text = sections.get("summary", "")
    if not summary_text:
        summary_text = f"Bệnh {vi_name} ({en_name}) theo tài liệu lâm sàng Andrews' Diseases of the Skin."

    diff_details = sections["differential"]
    if not diff_details and byt_reference:
        diff_details = byt_reference.get("differential_diagnosis_details", "")
    elif diff_details:
        diff_details = f"Chẩn đoán phân biệt theo Andrews: {diff_details[:400]}"

    return {
        "id": f"{disease_id}_andrews",
        "name": vi_name,
        "english_name": en_name,
        "type": chapter_title,
        "summary": summary_text.replace("\n", " "),
        "common_features": common_features,
        "suggestive_phrases": suggestive_phrases,
        "typical_locations": typical_locations,
        "course": "Diễn tiến lâm sàng theo phân loại Andrews' Diseases of the Skin.",
        "risk_factors": byt_reference.get("risk_factors", []) if byt_reference else [],
        "differential_diagnoses": differential_diagnoses,
        "differential_diagnosis_details": diff_details.replace("\n", " "),
        "red_flags": red_flags if red_flags else ["lan_nhanh", "sot_cao", "nhiem_trung"],
        "safe_advice": safe_advice if safe_advice else [
            f"Thực hiện chăm sóc da theo hướng dẫn của bác sĩ chuyên khoa da liễu.",
            f"Tránh cào gãi mạnh hoặc tự ý sử dụng các thuốc bôi không rõ nguồn gốc.",
            f"Đi khám chuyên khoa da liễu để được chẩn đoán và theo dõi phác đồ điều trị."
        ],
        "references": [
            {
                "source_id": "andrews_2015",
                "page_start": start_page,
                "title": "Andrews' Diseases of the Skin: Clinical Dermatology (12th Edition)",
                "publisher": "Elsevier",
                "year": 2015
            }
        ],
        "medical_review_status": "needs_clinical_review"
    }


def main():
    if not PDF_PATH or not PDF_PATH.exists():
        print(f"[ERROR] Không tìm thấy file PDF: {PDF_PATH}")
        sys.exit(1)

    if not TOC_PATH.exists():
        print(f"[ERROR] Chưa có file mục lục: {TOC_PATH}. Vui lòng chạy 01_extract_toc.py trước!")
        sys.exit(1)

    print(f"[INFO] Đọc mục lục từ {TOC_PATH}...")
    toc_entries = json.loads(TOC_PATH.read_text(encoding="utf-8"))

    byt_diseases = []
    if BYT_PATH.exists():
        byt_diseases = json.loads(BYT_PATH.read_text(encoding="utf-8"))
        print(f"[INFO] Đọc {len(byt_diseases)} bệnh mốc từ BYT...")

    reader = PdfReader(str(PDF_PATH))
    records = []

    # Map các bệnh trọng tâm từ BYT sang mục lục Andrews
    for b in byt_diseases:
        en = b.get("english_name", "").strip().lower()
        vi = b.get("name", "")
        bid = b.get("id", "")
        if not en:
            continue

        # Tìm entry trong TOC
        matches = [
            item for item in toc_entries
            if en == item["title"].lower() or item["title"].lower().startswith(en) or en in item["title"].lower()
        ]
        if not matches:
            continue

        # Chọn entry có tiêu đề gần nhất
        best = min(matches, key=lambda x: len(x["title"]))
        start_p = best["start_page"]
        end_p = best["end_page"]
        chapter = best["hierarchy"][0] if best["hierarchy"] else best["title"]

        # Trích xuất text từ các trang
        raw_text = extract_pages_text(reader, start_p, end_p, max_pages=3)
        if not raw_text or len(raw_text) < 100:
            continue

        record = build_disease_record(
            disease_id=bid,
            vi_name=vi,
            en_name=best["title"],
            chapter_title=chapter,
            start_page=start_p,
            raw_text=raw_text,
            byt_reference=b
        )
        records.append(record)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[HOÀN TẤT] Đã tạo thành công {len(records)} bệnh từ sách Andrews ra: {OUT_PATH}")


if __name__ == "__main__":
    main()
