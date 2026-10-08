"""Gắn mục lục vào trang thật"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from . import hierarchy
from .textutil import norm, upper_ratio

PREFIX_SCORE = 0.95  # độ giống quy ước cho dòng mở đầu bằng đúng tiêu đề (xem `_prefix_hit`)
MAX_PREFIX_LINE = 600  # dòng dài hơn thế không còn là "tiêu đề dính liền đoạn văn"
ANCHOR_CUTOFF = 0.82  # độ giống tối thiểu để coi một dòng là tiêu đề của mục
OFFSET_CUTOFF = 0.88  # chặt hơn: dùng để bỏ phiếu độ lệch, một lần khớp sai làm lệch cả sách
MIN_VOTES = 3

Line = tuple[int, int, str]  # (trang, chỉ số dòng, chữ chuẩn hoá)


def heading_lines(rows: list[dict[str, Any]], skip: set[int]) -> list[Line]:
    """Các dòng ngắn của thân sách (bỏ trang mục lục và trang nhiễu): ứng viên để khớp tên mục."""
    out: list[Line] = []
    for r in rows:
        if r.get("noise") or r["page"] in skip:
            continue
        for i, line in enumerate(r["text"].split("\n")):
            s = line.strip().lstrip("• ")
            if 4 <= len(s) <= 110:
                n = norm(s)
                if len(n) >= 4:
                    out.append((r["page"], i, n))
    return out


def prefix_lines(rows: list[dict[str, Any]], skip: set[int]) -> dict[int, list[tuple[int, str]]]:
    """Mọi dòng của thân sách theo trang"""
    out: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        if r.get("noise") or r["page"] in skip:
            continue
        for i, line in enumerate(r["text"].split("\n")):
            s = line.strip().lstrip("• ")
            if 4 <= len(s) <= MAX_PREFIX_LINE:
                out[r["page"]].append((i, s[:200]))
    return out


def _prefix_hit(title: str, tn: str, raw: str) -> bool:
    """Dòng mở đầu bằng đúng tiêu đề VIẾT HOA"""
    if len(tn) < 6:
        return False
    head = norm(raw[: len(title) + 6])
    return head.startswith(tn) and (len(head) == len(tn) or head[len(tn)] == " ") and upper_ratio(raw[: len(title)]) >= 0.8


def _index(lines: list[Line]) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = defaultdict(list)
    for k, (_, _, n) in enumerate(lines):
        for tok in set(n.split()):
            if len(tok) >= 5:
                idx[tok].append(k)
    return idx


def _close_len(a: str, b: str) -> bool:
    return abs(len(a) - len(b)) <= max(6, len(a) * 0.4)


def _matches(title_norm: str, lines: list[Line], idx: dict[str, list[int]], cutoff: float) -> list[tuple[int, int, float]]:
    """(trang, dòng, độ giống) các dòng giống tên mục; chỉ so với dòng chứa một từ dài của tên (khỏi so mọi dòng)."""
    toks = sorted({t for t in title_norm.split() if len(t) >= 5}, key=len, reverse=True)[:2]
    out = []
    for k in {k for t in toks for k in idx.get(t, [])}:
        page, line, n = lines[k]
        if _close_len(title_norm, n):
            r = SequenceMatcher(None, title_norm, n).ratio()
            if r >= cutoff:
                out.append((page, line, r))
    return out


def estimate_offset(rows: list[dict[str, Any]], entries: list[dict[str, Any]], skip: set[int]) -> tuple[int | None, dict[str, Any]]:
    """Bỏ phiếu độ lệch. Trả (độ lệch | None, thông tin để hiển thị cho người duyệt)."""
    lines = heading_lines(rows, skip)
    if not lines:
        return None, {"matched": 0}
    idx = _index(lines)
    votes: Counter[int] = Counter()
    matched = 0
    for e in entries:
        if e.get("printed_page") is None or e.get("suspect"):
            continue
        tn = norm(e["title"])
        if len(tn) < 8:
            continue
        hits = _matches(tn, lines, idx, OFFSET_CUTOFF)
        if hits and len({p for p, _, _ in hits}) <= 3:  # tên lặp ở nhiều trang (vd nhãn) không đủ tin
            matched += 1
            for p, _, _ in hits:
                votes[p - e["printed_page"]] += 1
    if not votes:
        return None, {"matched": matched}
    (off, n), *_ = votes.most_common(1)
    total = sum(votes.values())
    info = {"matched": matched, "votes": dict(votes.most_common(5)), "support": n}
    if n < MIN_VOTES or n < 0.4 * total:
        return None, info
    return int(off), info


def _best_line(title: str, by_page: dict[int, list[tuple[int, str]]], longs: dict[int, list[tuple[int, str]]],
               pages: list[int]) -> tuple[float, int | None, int | None]:
    """Dòng giống tên mục nhất trong các `pages` (trang đầu danh sách được ưu tiên nhẹ)."""
    tn = norm(title)
    best: tuple[float, int | None, int | None] = (0.0, None, None)
    for rank, p in enumerate(pages):
        pen = 0.02 if rank else 0
        for ln, n in by_page.get(p, []):
            if _close_len(tn, n):
                r = SequenceMatcher(None, tn, n).ratio() - pen
                if r > best[0]:
                    best = (r, p, ln)
        for ln, raw in longs.get(p, []):
            if PREFIX_SCORE - pen > best[0] and _prefix_hit(title, tn, raw):
                best = (PREFIX_SCORE - pen, p, ln)
    return best


def anchor(entries: list[dict[str, Any]], rows: list[dict[str, Any]], offset: int, skip: set[int], total: int) -> int:
    """Gán `pdf_page`, `anchor_line`, `anchored`, `out_of_range` cho từng mục (sửa tại chỗ). Trả số mục đã neo."""
    by_page: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for p, ln, n in heading_lines(rows, skip):
        by_page[p].append((ln, n))
    longs = prefix_lines(rows, skip)
    anchored = 0
    prev_page = 1
    for e in entries:
        e["pdf_page"] = e["anchor_line"] = None
        e["anchored"] = e["out_of_range"] = False
        if e.get("printed_page") is None:
            continue
        exp = e["printed_page"] + offset
        if total and exp > total:  # PDF chỉ là một phần của sách: mục này nằm ngoài các trang đang có
            e["out_of_range"], e["pdf_page"] = True, exp
            continue
        r, p, ln = _best_line(e["title"], by_page, longs, [exp, exp - 1, exp + 1])
        if r >= ANCHOR_CUTOFF and p is not None:
            e["pdf_page"], e["anchor_line"], e["anchored"] = p, ln, True
            anchored += 1
        else:
            e["pdf_page"] = exp
        if e["pdf_page"] < prev_page:  # trang lùi (OCR sai số trang): giữ thứ tự đọc và báo
            e["pdf_page"], e["suspect"] = prev_page, True
            e["suspect_reason"] = e.get("suspect_reason") or "số trang lùi so với mục trước"
        prev_page = max(prev_page, e["pdf_page"])
    # part/section không có số trang: bắt đầu cùng trang với mục con đầu tiên; thử neo bằng chính tiêu đề của nó
    nxt: int | None = None
    for e in reversed(entries):
        if e.get("pdf_page") is not None:
            nxt = e["pdf_page"]
        elif e.get("printed_page") is None and nxt is not None:
            e["pdf_page"] = nxt
            r, p, ln = _best_line(e["title"], by_page, longs, [nxt, nxt - 1])
            if r >= ANCHOR_CUTOFF and p is not None:
                e["pdf_page"], e["anchor_line"], e["anchored"] = p, ln, True
                anchored += 1
    return anchored


KINDS = {0: "part", 1: "section", 2: "topic", 3: "sub"}


def apply_overrides(entries: list[dict[str, Any]], ov: dict[str, Any]) -> list[dict[str, Any]]:
    """Áp override của người duyệt (sửa / xoá / thêm mục) lên danh sách mục máy đọc."""
    deleted = set(ov.get("_deleted") or [])
    out: list[dict[str, Any]] = []
    for e in entries:
        if e["id"] in deleted:
            continue
        x = dict(e)
        o = ov.get(e["id"]) or {}
        for k in ("title", "level", "printed_page"):
            if k in o:
                x[k] = o[k]
        if "level" in o:
            x["kind"] = KINDS.get(int(o["level"]), "topic")
        x["edited"] = bool(o)
        if x["edited"] and "printed_page" in o:
            x["suspect"] = False
        out.append(x)
    for a in ov.get("_added") or []:
        lvl = max(0, min(int(a.get("level", 2)), 3))
        new = {"id": a["id"], "level": lvl, "kind": KINDS[lvl], "title": a.get("title", ""), "printed_page": a.get("printed_page"),
               "toc_page": None, "edited": True, "added": True, "suspect": False}
        pos = next((i + 1 for i, e in enumerate(out) if e["id"] == a.get("after")), len(out))
        out.insert(pos, new)
    return out


def build_toc(auto: dict[str, Any], overrides: dict[str, Any], rows: list[dict[str, Any]], total_pages: int) -> dict[str, Any]:
    """Áp override lên kết quả AI (`toc.auto.json`), dựng cây + độ lệch + neo -> nội dung `toc.json` (hàm thuần, không ghi file)."""
    entries = apply_overrides(auto["entries"], overrides)
    skip = set(auto["toc_pages"])
    if overrides.get("_offset") is not None:
        off, info = int(overrides["_offset"]), {"source": "user"}
    else:
        off, info = estimate_offset(rows, entries, skip)
        info["source"] = "auto"
    hierarchy.build_tree(entries)
    anchored = anchor(entries, rows, off, skip, total_pages) if off is not None else 0
    warnings = list(auto.get("meta", {}).get("warnings", []))
    if off is None:
        warnings.append("Chưa xác định được độ chênh lệch giữa số trang in và số trang trong file PDF: hãy nhập tay, "
                        "hoặc làm bước Đọc nội dung để hệ thống tự tính.")
    return {"toc_pages": auto["toc_pages"], "pages_source": auto.get("pages_source", ""), "entries": entries, "offset": off,
            "offset_info": info, "total_pages": total_pages, "anchored": anchored, "warnings": warnings}
