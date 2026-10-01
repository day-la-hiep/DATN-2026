#!/usr/bin/env python3
"""01_extract_toc.py - Giai đoạn 1: Bóc tách cấu trúc Bookmark/Mục lục từ PDF Andrews 2015.

Input : Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf (ở repo root hoặc input/)
Output: core/data_ingest/andrews/output/andrews_toc.json
"""
import io
import json
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

# Tìm file PDF
CANDIDATE_PDFS = [
    REPO_ROOT / "Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf",
    ANDREWS_DIR / "input" / "Andrews_Diseases_of_the_Skin_-_Clinical_Dermatology_2015.pdf",
    ANDREWS_DIR / "input" / "andrews.pdf",
]

PDF_PATH = next((p for p in CANDIDATE_PDFS if p.exists()), None)
OUT_PATH = ANDREWS_DIR / "output" / "andrews_toc.json"


def traverse_outline(reader: PdfReader, outline, parent_chain=()) -> list[dict]:
    """Duyệt đệ quy cây bookmark, bảo tồn thứ tự và phân cấp cha-con."""
    res = []
    i = 0
    while i < len(outline):
        item = outline[i]
        if not isinstance(item, list):
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = None
            title = item.title.strip() if item.title else ""
            current = {
                "title": title,
                "page": page,
                "hierarchy": list(parent_chain),
            }
            res.append(current)
            if i + 1 < len(outline) and isinstance(outline[i + 1], list):
                res.extend(traverse_outline(reader, outline[i + 1], parent_chain + (title,)))
                i += 1
        i += 1
    return res


def main():
    if not PDF_PATH:
        print("[ERROR] Không tìm thấy file PDF Andrews!")
        print("Đường dẫn đã tìm:")
        for p in CANDIDATE_PDFS:
            print(f"  - {p}")
        sys.exit(1)

    print(f"[INFO] Đọc file PDF: {PDF_PATH} ({PDF_PATH.stat().st_size / (1024*1024):.1f} MB)")
    reader = PdfReader(str(PDF_PATH))
    total_pages = len(reader.pages)
    print(f"[INFO] Tổng số trang PDF: {total_pages}")

    if not reader.outline:
        print("[ERROR] PDF không có outline/bookmarks!")
        sys.exit(1)

    entries = traverse_outline(reader, reader.outline)
    print(f"[INFO] Bóc tách được {len(entries)} mục từ Bookmark")

    # Tính end_page cho từng entry (dựa trên page của mục kế tiếp có page > page hiện tại)
    entries_with_pages = [e for e in entries if e["page"] is not None]
    for i, e in enumerate(entries_with_pages):
        current_page = e["page"]
        end_page = total_pages
        # Tìm mục tiếp theo cùng cấp hoặc cấp trên có page lớn hơn
        for j in range(i + 1, len(entries_with_pages)):
            next_page = entries_with_pages[j]["page"]
            if next_page and next_page > current_page:
                end_page = next_page
                break
        e["start_page"] = current_page
        e["end_page"] = end_page

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(entries_with_pages, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Đã ghi chỉ mục TOC ra: {OUT_PATH}")

    # Thống kê nhanh các chương
    chapters = [e for e in entries_with_pages if len(e["hierarchy"]) == 0 and e["title"] and e["title"][0].isdigit()]
    print(f"\n=== ĐÃ BÓC TÁCH {len(chapters)} CHƯƠNG CHÍNH ===")
    for c in chapters[:10]:
        print(f"  {c['title']:<70} (tr. {c['start_page']} -> {c['end_page']})")
    if len(chapters) > 10:
        print(f"  ... và {len(chapters) - 10} chương khác.")


if __name__ == "__main__":
    main()
