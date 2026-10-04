"""Các bước của pipeline `document_ingest`: thứ tự, phụ thuộc, đầu ra. Hằng nghiệp vụ, dùng chung cho repository, runner và API."""
from typing import Any

# Thứ tự bước + phụ thuộc. Một bước chỉ chạy được khi mọi bước phụ thuộc đã `approved`.
# `toc` không phụ thuộc `ingest`: đọc mục lục chỉ cần vài chục trang (OCR riêng các trang đó), nên người dùng thử được
# ngay mà không đợi OCR cả tài liệu. Độ lệch + neo cần chữ thân tài liệu nên được tính lại khi có `pages.jsonl` (xem mapping.py).
STAGES: list[dict[str, Any]] = [
    {"id": "ingest", "title": "Đọc nội dung", "deps": [], "llm": False, "outputs": ["pages.jsonl"]},
    {"id": "toc", "title": "Mục lục", "deps": [], "llm": True, "outputs": ["toc.auto.json", "toc.json"]},
    {"id": "chunks", "title": "Chia đoạn", "deps": ["ingest", "toc"], "llm": False, "outputs": ["chunks.jsonl"]},
    {"id": "index", "title": "Lưu vào kho tri thức", "deps": ["chunks"], "llm": False, "outputs": ["index.json"]},
]
# Trạng thái: not_started -> running -> pending_review -> approved ; failed/cancelled khi lỗi ; stale khi bước thượng nguồn
# chạy lại sau khi bước này đã có kết quả.
STAGE_IDS = [s["id"] for s in STAGES]
STAGE_BY_ID = {s["id"]: s for s in STAGES}



def downstream(stage_id: str) -> list[str]:
    """Mọi bước (gián tiếp) phụ thuộc `stage_id`."""
    out: list[str] = []
    changed = True
    tainted = {stage_id}
    while changed:
        changed = False
        for s in STAGES:
            if s["id"] not in tainted and any(d in tainted for d in s["deps"]):
                tainted.add(s["id"])
                out.append(s["id"])
                changed = True
    return out
