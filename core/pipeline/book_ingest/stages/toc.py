"""Mục lục — LLM tìm trang mục lục rồi đọc thành cây part/section/mục kèm số trang in (bước 1 của luồng).

1. Trang mục lục: người dùng chỉ định (`pages=8-22`) thì dùng luôn; không thì LLM đọc bản tóm tắt các trang đầu/cuối.
2. LLM đọc từng nhóm vài trang mục lục (OCR nhiễu, bảng Markdown) -> các mục theo thứ tự: cấp (0 part, 1 section,
   2 mục/bệnh, 3 mục con), tên, số trang in. Nhóm sau nhận ngữ cảnh part/section cuối của nhóm trước.
3. Kiểm tra bằng luật: số trang phải tăng dần; mục phá thứ tự (hay là OCR sai chữ số) bị đánh dấu `suspect`.
4. Gắn vào trang thật (độ lệch + neo) KHÔNG nằm ở đây mà ở `mapping.py` (luật, không LLM); chạy lại rẻ mỗi khi
   người duyệt sửa hay có dữ liệu trang mới.

Ra: `toc.auto.json` (kết quả máy, giữ nguyên) và `toc.json` (đã áp override + độ lệch + neo).
Override của người duyệt (bảng `book_overrides`, stage `toc`):
  { "<id>": {"title": ..., "level": ..., "printed_page": ...},
    "_deleted": ["<id>", ...],
    "_added": [{"id": "x1", "title": ..., "level": ..., "printed_page": ..., "after": "<id>"|null}],
    "_offset": 30 }"""
import json
import subprocess
from collections import Counter
from typing import Any

from .. import mapping
from app.infra.llm_client import LLMError
from ..textutil import parse_page_ranges
from . import StageContext, StageError, refresh_toc

DIGEST_HEAD_PAGES = 60
DIGEST_TAIL_PAGES = 15

FIND_PROMPT = """Bạn nhận bản tóm tắt các trang đầu và cuối của một cuốn sách (PDF; OCR có thể nhiễu, bảng ở dạng Markdown). Hãy tìm các trang là MỤC LỤC (danh sách tên phần/chương/mục kèm số trang), thường nằm liền nhau gần đầu sách (đôi khi sau lời nói đầu). Mỗi trang có: page (số trang PDF), chars (số ký tự), head (220 ký tự đầu).

Quy tắc:
- Trang đầu của mục lục thường có chữ CONTENTS / MỤC LỤC / TABLE OF CONTENTS; các trang sau chỉ là các hàng "tên | số trang".
- Không tính lời nói đầu, lời cảm ơn, danh sách hình/bảng, hay mục từ (index) cuối sách.
- Chỉ dùng thông tin được cung cấp; không chắc thì để trống.

Trả về DUY NHẤT JSON hợp lệ: {"toc_pages": [8, 9, 10], "reason": "≤ 15 từ"}"""

PARSE_PROMPT = """Bạn đọc các trang MỤC LỤC của một cuốn sách (OCR có thể nhiễu; bảng ở dạng Markdown "| tên | số trang |") và chuyển thành danh sách mục theo ĐÚNG thứ tự đọc.

Mỗi mục: {"level": 0-3, "title": "...", "printed_page": 123 hoặc null}
- level 0 = PART (phần lớn, vd "PART IV ..."), 1 = SECTION (nhóm/chương, vd "SECTION 2 ECZEMA/DERMATITIS"), 2 = mục/bệnh/chương con có số trang, 3 = mục con thụt vào dưới một mục level 2.
- Tên mục lấy nguyên văn, chỉ sửa lỗi OCR RÕ RÀNG (chữ bị thay ký tự, vd "Lupua Erythematolus" -> "Lupus Erythematosus"); không thêm, bỏ hay gộp mục. Dòng tiêu đề bị ngắt thành nhiều dòng thì gộp một mục.
- printed_page là số trang IN của sách (số Ả Rập). Số La Mã (xxiii) hoặc không có số thì null.
- Bỏ các dòng không phải mục: chữ CONTENTS/MỤC LỤC, tên sách, số trang đứng một mình, dòng kẻ bảng.
- "context" là part/section cuối của nhóm trang trước: dùng để biết mục đầu nhóm này thuộc đâu; KHÔNG lặp lại context thành mục.

Trả về DUY NHẤT JSON hợp lệ: {"entries": [{"level": 1, "title": "...", "printed_page": 61}]}"""


# ---------------------------------------------------------------- đọc chữ các trang
def _total_pages(ctx: StageContext) -> int:
    rows = ctx.store.files.read_jsonl("pages.jsonl")
    if rows:
        return max(r["page"] for r in rows)
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(ctx.local_pdf())).pages)
    except Exception as e:
        raise StageError(f"Không đọc được PDF: {e}") from e


def _pdftotext_pages(ctx: StageContext, first: int, last: int) -> dict[int, str]:
    try:
        out = subprocess.run(["pdftotext", "-f", str(first), "-l", str(last), "-layout", str(ctx.local_pdf()), "-"],
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise StageError(f"pdftotext lỗi: {e}") from e
    return {first + i: t for i, t in enumerate(out.split("\f")[: last - first + 1])}


def _digests(ctx: StageContext) -> list[dict[str, Any]]:
    total = _total_pages(ctx)
    wanted = sorted(set(range(1, min(total, DIGEST_HEAD_PAGES) + 1)) | set(range(max(1, total - DIGEST_TAIL_PAGES + 1), total + 1)))
    rows = {r["page"]: r["text"] for r in ctx.store.files.read_jsonl("pages.jsonl")}
    if not rows:
        rows = _pdftotext_pages(ctx, 1, total)  # chưa ingest: lớp text ẩn của PDF (có thể kém) đủ để nhận ra trang mục lục
    return [{"page": n, "chars": len(rows.get(n, "")), "head": " ".join(rows.get(n, "").split())[:220]} for n in wanted]


def page_texts(ctx: StageContext, pages: list[int]) -> dict[int, str]:
    """Chữ các trang mục lục: dùng pages.jsonl nếu đã ingest; chưa thì OCR riêng các trang này bằng Docling (engine docling)
    hoặc lớp text của PDF (engine pdftotext)."""
    have = {r["page"]: r["text"] for r in ctx.store.files.read_jsonl("pages.jsonl")}
    if all(p in have for p in pages):
        return {p: have[p] for p in pages}
    if ctx.profile.extraction.engine == "docling":
        out: dict[int, str] = {}
        runs: list[list[int]] = []
        for p in sorted(pages):
            if runs and p == runs[-1][-1] + 1:
                runs[-1].append(p)
            else:
                runs.append([p])
        for run in runs:
            ctx.progress(0, 1, f"Docling OCR trang mục lục {run[0]}-{run[-1]}")
            blocks = ctx.require_docling().convert_pages(ctx.local_pdf(), run[0], run[-1], ocr=True,
                                   force_ocr=ctx.profile.extraction.docling_force_ocr, tables=True)
            for b in blocks:
                if b["label"] in {"heading", "text", "list", "caption", "table", "toc"}:
                    out[b["page"]] = (out.get(b["page"], "") + "\n" + " ".join(b["text"].split())).strip("\n")
        return {p: out.get(p, "") for p in pages}
    got = _pdftotext_pages(ctx, min(pages), max(pages))
    return {p: got.get(p, "") for p in pages}


# ---------------------------------------------------------------- LLM
def find_toc_pages(ctx: StageContext) -> tuple[list[int], str]:
    llm = ctx.require_llm()
    digests = _digests(ctx)
    try:
        data = llm.complete_json(FIND_PROMPT, "Các trang (JSON):\n" + json.dumps(digests, ensure_ascii=False), name="toc_find")
    except LLMError as e:
        raise StageError(f"AI không xác định được trang mục lục: {e}") from e
    raw = data.get("toc_pages") if isinstance(data, dict) else None
    pages = sorted({int(p) for p in raw if str(p).isdigit()}) if isinstance(raw, list) else []
    if not pages:
        raise StageError("AI không tìm thấy trang mục lục — hãy nhập số trang mục lục (vd 8-22) rồi thử lại.")
    return pages, str((data or {}).get("reason") or "")[:160]


def _clean_entry(it: Any) -> dict[str, Any] | None:
    if not isinstance(it, dict):
        return None
    title = " ".join(str(it.get("title") or "").split()).strip(" |-.")
    if len(title) < 2:
        return None
    try:
        level = max(0, min(int(it.get("level", 2)), 3))
    except (TypeError, ValueError):
        level = 2
    page = it.get("printed_page")
    page = int(page) if isinstance(page, (int, float)) or (isinstance(page, str) and page.strip().isdigit()) else None
    return {"level": level, "kind": mapping.KINDS[level], "title": title, "printed_page": page}


def parse_entries(ctx: StageContext, texts: dict[int, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """LLM đọc các trang mục lục theo nhóm, tuần tự (nhóm sau cần part/section cuối của nhóm trước)."""
    llm = ctx.require_llm()
    warnings: list[str] = []
    groups: list[list[int]] = []
    size = 0
    for p in sorted(texts):
        n = len(texts[p])
        if groups and (len(groups[-1]) >= 3 or size + n > 9000):
            groups.append([])
            size = 0
        if not groups:
            groups.append([])
        groups[-1].append(p)
        size += n
    entries: list[dict[str, Any]] = []
    context: dict[str, str] = {}

    def ask(pages: list[int]) -> list[dict[str, Any]]:
        payload = {"context": context, "pages": [{"page": p, "text": texts[p][:7000]} for p in pages]}
        try:
            data = llm.complete_json(PARSE_PROMPT, "Dữ liệu (JSON):\n" + json.dumps(payload, ensure_ascii=False), name="toc_parse")
        except LLMError as e:
            if len(pages) == 1:
                warnings.append(f"AI không đọc được trang mục lục {pages[0]}: {str(e)[:100]}")
                return []
            ctx.log(f"nhóm trang {pages} lỗi -> đọc từng trang")
            return [x for p in pages for x in ask([p])]
        items = data.get("entries") if isinstance(data, dict) else data
        out = []
        for it in items or []:
            e = _clean_entry(it)
            if e is not None:
                e["toc_page"] = pages[0] if len(pages) == 1 else None
                out.append(e)
        return out

    for i, g in enumerate(groups, 1):
        ctx.progress(i - 1, len(groups), f"LLM đọc mục lục: trang {g[0]}-{g[-1]}")
        got = ask(g)
        for e in got:
            if e["level"] == 0:
                context = {"part": e["title"]}
            elif e["level"] == 1:
                context = {**context, "section": e["title"]}
        entries += got
    for n, e in enumerate(entries, 1):
        e["id"] = f"t{n:04d}"
    return entries, warnings


def flag_suspects(entries: list[dict[str, Any]]) -> int:
    """Số trang in phải tăng dần. Giữ dãy không giảm dài nhất; mục ngoài dãy đó (hay là chữ số bị OCR sai) bị đánh dấu."""
    idx = [i for i, e in enumerate(entries) if e.get("printed_page") is not None]
    pages = [entries[i]["printed_page"] for i in idx]
    n = len(pages)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pages[j] <= pages[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    keep: set[int] = set()
    k = max(range(n), key=lambda i: best[i], default=-1)
    while k >= 0:
        keep.add(k)
        k = prev[k]
    flagged = 0
    for pos, i in enumerate(idx):
        bad = pos not in keep
        entries[i]["suspect"] = bad
        if bad:
            entries[i]["suspect_reason"] = "số trang không tăng dần (có thể đọc sai chữ số)"
            flagged += 1
    return flagged


# ---------------------------------------------------------------- chạy / hiệu lực
def run(ctx: StageContext) -> dict:
    explicit = str(ctx.options.get("pages", "")).strip()
    total = _total_pages(ctx)
    ctx.progress(0, 3, "xác định trang mục lục")
    if explicit:
        pages = sorted(parse_page_ranges([x for x in explicit.split(",")], total))
        if not pages:
            raise StageError(f"Số trang mục lục không hợp lệ: {explicit!r} (ví dụ đúng: 8-22)")
        source, reason = "user", "do bạn nhập"
    else:
        pages, reason = find_toc_pages(ctx)
        source = "llm"
    ctx.log(f"trang mục lục ({source}): {pages[0]}-{pages[-1]} ({len(pages)} trang) — {reason}")
    ctx.progress(1, 3, "đọc chữ các trang mục lục")
    texts = page_texts(ctx, pages)
    if not any(t.strip() for t in texts.values()):
        raise StageError("Các trang mục lục không có chữ — hãy kiểm tra lại số trang, hoặc chọn cách đọc “nhận dạng chữ từ ảnh” trong Cài đặt.")
    entries, warnings = parse_entries(ctx, texts)
    if not entries:
        raise StageError("AI không đọc ra mục nào từ các trang mục lục.")
    flagged = flag_suspects(entries)
    if flagged:
        warnings.append(f"{flagged} mục có số trang không tăng dần theo thứ tự mục lục (thường do đọc sai chữ số) — vui lòng kiểm tra các mục được tô vàng.")
    ctx.store.files.write_json("toc.auto.json", {"toc_pages": pages, "pages_source": source, "entries": entries,
                                           "meta": {"warnings": warnings, "reason": reason}})
    return reapply(ctx)


def reapply(ctx: StageContext) -> dict:
    """Áp override + tính lại độ lệch/neo (không LLM). Gọi sau mỗi lần người duyệt sửa."""
    has_text = ctx.store.files.exists("source.pdf") or ctx.store.files.exists("pages.jsonl")
    refresh_toc(ctx, _total_pages(ctx) if has_text else 0)
    doc = ctx.store.files.read_json("toc.json")
    ents = doc["entries"]
    by_level = Counter(e["level"] for e in ents)
    summary: dict[str, Any] = {
        "toc_pages": f"{doc['toc_pages'][0]}-{doc['toc_pages'][-1]}", "pages_source": doc["pages_source"], "entries": len(ents),
        "parts": by_level.get(0, 0), "sections": by_level.get(1, 0), "topics": by_level.get(2, 0) + by_level.get(3, 0),
        "suspect": sum(1 for e in ents if e.get("suspect")), "offset": doc["offset"], "anchored": doc["anchored"],
    }
    if doc["warnings"]:
        summary["warnings"] = doc["warnings"]
    if ctx.llm is not None:
        summary["llm"] = ctx.llm.stats
    return summary
