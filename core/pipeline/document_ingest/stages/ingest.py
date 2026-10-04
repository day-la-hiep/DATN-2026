"""Ingest — PDF -> chữ theo trang (`pages.jsonl`), không LLM.

Mỗi dòng của `pages.jsonl`: {page, page_printed, header, text, noise, noise_reason, noise_score}. `text` là các dòng nối
bằng "\\n"; chỉ số dòng này là toạ độ "neo" của mục lục (mapping.py) và của chunk.

Hai engine (profile.extraction.engine): `pdftotext` (lớp text có sẵn, nhanh) và `docling` (OCR ảnh trang, theo cụm trang
có checkpoint). Running header lặp và số trang in ở chân trang được tách khỏi `text`."""
import re
import subprocess
from collections import Counter
from typing import Any

from ..textutil import noise_score, parse_page_ranges, upper_ratio
from . import StageContext, StageError

_BODY_LABELS = {"heading", "text", "list", "caption", "table", "toc"}


def _head_key(line: str) -> str:
    return re.sub(r"[^A-Z]", "", line.upper())[:14]


def _page_range(spec: object, total: int) -> tuple[int, int]:
    """Option `pages` ("1-300", "40") -> (đầu, cuối) trong [1, total]."""
    if not spec:
        return 1, total
    a, _, b = str(spec).strip().partition("-")
    try:
        lo, hi = int(a), int(b or a)
    except ValueError as e:
        raise StageError(f"Option pages không hợp lệ: {spec!r} (vd '1-300')") from e
    lo, hi = max(1, lo), min(total, hi)
    if lo > hi:
        raise StageError(f"Khoảng trang {spec!r} nằm ngoài sách ({total} trang)")
    return lo, hi


def _row(n: int, header: str, printed: int | None, text: str, noise_set: set[int], offset: int) -> dict[str, Any]:
    reason = "profile" if n in noise_set else ("index" if _head_key(header) == "INDEX" else None)
    return {"page": n, "page_printed": printed if printed is not None else n + offset, "header": header, "text": text,
            "noise": reason is not None, "noise_reason": reason, "noise_score": noise_score(text)}


def _save_figures(files: Any, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ghi ảnh hình minh hoạ ra `figures/` rồi thay bytes bằng `image_key` để part JSON vẫn serialize được."""
    per_page: Counter[int] = Counter()
    for blk in blocks:
        png = blk.pop("image_png", None)
        if blk["label"] != "figure" or png is None:
            continue
        per_page[blk["page"]] += 1
        blk["image_key"] = f"figures/p{blk['page']:05d}_{per_page[blk['page']]:02d}.png"
        files.put_bytes(blk["image_key"], png, "image/png")
    return blocks


def _run_docling(ctx: StageContext) -> dict:
    from pypdf import PdfReader

    files, ext = ctx.files, ctx.profile.extraction
    pdf = ctx.local_pdf()
    total = len(PdfReader(str(pdf)).pages)
    first, last = _page_range(ctx.options.get("pages"), total)
    key = f"force_ocr={ext.docling_force_ocr};tables={ext.docling_tables}"
    if files.get_text("docling_parts/key.txt") not in (None, key):
        files.delete_prefix("docling_parts/")  # cấu hình đổi: kết quả cũ không dùng lại được
        files.delete_prefix("figures/")
    files.put_text("docling_parts/key.txt", key)

    step = ext.docling_chunk_pages
    spans = [(a, min(a + step - 1, last)) for a in range(first, last + 1, step)]
    for i, (a, b) in enumerate(spans, 1):
        part = f"docling_parts/part_{a:05d}_{b:05d}.json"
        ctx.progress(i - 1, len(spans), f"Nhận dạng chữ: trang {a}-{b}")
        if files.exists(part):  # đã đọc ở lần chạy trước (dừng/làm lại không mất)
            continue
        blocks = ctx.require_docling().convert_pages(pdf, a, b, force_ocr=ext.docling_force_ocr, tables=ext.docling_tables)
        files.write_json(part, _save_figures(files, blocks))
        ctx.log(f"trang {a}-{b}: {len(blocks)} khối")
    ctx.progress(len(spans), len(spans), "dựng pages.jsonl")

    by_page: dict[int, list[dict]] = {}
    for name in sorted(n for n in files.list_names("docling_parts/part_") if n.endswith(".json")):
        for blk in files.read_json(name, []):
            if first <= blk["page"] <= last:
                by_page.setdefault(blk["page"], []).append(blk)

    noise_set = parse_page_ranges(ext.noise_pages, total)
    rows = []
    for n in range(first, last + 1):
        blocks = by_page.get(n, [])
        header = " ".join(b["text"] for b in blocks if b["label"] == "page_header")
        printed = next((int(b["text"]) for b in blocks if b["label"] == "page_footer" and b["text"].strip().isdigit()), None)
        # bảng/mục lục là Markdown nhiều dòng: gộp một dòng để chỉ số dòng ổn định
        lines = [("• " if b["label"] == "list" else "") + " ".join(b["text"].split()) for b in blocks if b["label"] in _BODY_LABELS]
        rows.append(_row(n, header, printed, "\n".join(lines), noise_set, ext.page_offset))
    files.write_jsonl("pages.jsonl", rows)
    figures = _figure_rows(ctx.document_id, files, by_page, first, last)
    files.write_json("figures.json", figures)
    summary = _summary("docling", rows, first, last)
    summary["figures"] = len(figures)
    return summary


def _figure_rows(document_id: str, files: Any, by_page: dict[int, list[dict]], first: int, last: int) -> list[dict[str, Any]]:
    """Danh sách ảnh theo thứ tự trang -> `figures.json`, khớp field của `DocumentFigure` (dto/base).
    Khoá dùng tên Python gốc vì đây là file trong MinIO, không phải API response."""
    out: list[dict[str, Any]] = []
    for n in range(first, last + 1):
        for blk in by_page.get(n, []):
            if blk["label"] != "figure" or "image_key" not in blk:
                continue
            seq = len(out) + 1
            out.append({
                "figure_id": f"{document_id}:f{seq:05d}", "document_id": document_id, "page": n, "seq": seq,
                "bbox": blk.get("bbox"), "caption": blk["text"],
                "image_file": {"file_name": blk["image_key"].split("/")[-1], "storage_key": files.key(blk["image_key"]),
                               "content_type": "image/png"},
            })
    return out


def _run_pdftotext(ctx: StageContext) -> dict:
    files, ext = ctx.files, ctx.profile.extraction
    files.delete_prefix("figures/")  # pdftotext không trích ảnh; xoá ảnh của lần chạy docling trước (nếu có)
    files.write_json("figures.json", [])
    cmd = ["pdftotext"] + (["-layout"] if ext.layout else []) + [str(ctx.local_pdf()), "-"]
    ctx.log("chạy: " + " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except OSError as e:
        raise StageError(f"Không đọc được file PDF (máy chủ thiếu công cụ poppler-utils): {e}") from e
    if proc.returncode != 0:
        raise StageError(f"pdftotext lỗi: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    raw_pages = proc.stdout.decode("utf-8", "replace").split("\f")
    if raw_pages and not raw_pages[-1].strip():
        raw_pages.pop()
    total = len(raw_pages)
    if total == 0:
        raise StageError("PDF không có văn bản — với sách scan, hãy chọn “nhận dạng chữ từ ảnh” trong Cài đặt.")
    lines_by_page = [p.split("\n") for p in raw_pages]

    def first_idx(lines: list[str]) -> int | None:
        return next((i for i, ln in enumerate(lines) if ln.strip()), None)

    header_keys: set[str] = set()
    if ext.strip_running_headers:
        cnt: Counter[str] = Counter()
        for lines in lines_by_page:
            i = first_idx(lines)
            if i is not None and 4 <= len(lines[i].strip()) <= 110 and upper_ratio(lines[i].strip()) >= 0.6:
                cnt[_head_key(lines[i].strip())] += 1
        threshold = max(5, int(0.015 * total))
        header_keys = {k for k, n in cnt.items() if n >= threshold and k}
        ctx.log(f"{len(header_keys)} kiểu running header (ngưỡng ≥ {threshold} trang)")

    noise_set = parse_page_ranges(ext.noise_pages, total)
    rows = []
    for n, lines in enumerate(lines_by_page, 1):
        ctx.progress(n, total, "đọc trang")
        header = ""
        i = first_idx(lines)
        if i is not None and header_keys and _head_key(lines[i].strip()) in header_keys:
            header, lines = lines[i].strip(), lines[i + 1:]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        printed: int | None = None
        if lines and re.fullmatch(r"\s*\d{1,4}\s*", lines[-1]):  # số trang in ở cuối trang
            printed, lines = int(lines[-1].strip()), lines[:-1]
        while lines and not lines[0].strip():
            lines = lines[1:]
        rows.append(_row(n, header, printed, "\n".join(lines).rstrip(), noise_set, ext.page_offset))
    files.write_jsonl("pages.jsonl", rows)
    return _summary("pdftotext", rows, 1, total)


def _summary(engine: str, rows: list[dict], first: int, last: int) -> dict:
    """Summary đi thẳng ra API/FE (snake_case)."""
    return {
        "engine": engine, "pages": len(rows), "page_range": [first, last],
        "pages_skipped": sum(1 for r in rows if r["noise"]),
        "pages_empty": sum(1 for r in rows if not r["text"].strip()),
        "pages_high_noise": sum(1 for r in rows if r["noise_score"] > 0.05),
    }


def run(ctx: StageContext) -> dict:
    if not ctx.files.exists("source.pdf"):
        raise StageError("Không tìm thấy file PDF của sách.")
    return _run_docling(ctx) if ctx.profile.extraction.engine == "docling" else _run_pdftotext(ctx)
