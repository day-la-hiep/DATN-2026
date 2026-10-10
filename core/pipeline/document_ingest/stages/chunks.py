"""Chunk theo khung mục lục"""
import re
from bisect import bisect_right
from typing import Any

from .. import hierarchy, mapping
from app.models.document_profile import ChunkingConfig
from . import StageContext, StageError, refresh_toc

_SENT = re.compile(r"(?<=[.!?])\s+")


def est_tokens(text: str) -> int:
    """Ước lượng token (không dùng tokenizer thật): lớn hơn của ~1.3 token/từ và ~1 token/4 ký tự."""
    return int(max(len(text.split()) * 1.3, len(text) / 4)) + 1


def split_unit(text: str, max_tokens: int) -> list[str]:
    """Một khối chữ dài quá mức: cắt theo câu, câu quá dài cắt theo từ."""
    out: list[str] = []
    cur = ""
    for sent in _SENT.split(text):
        words = sent.split()
        while est_tokens(" ".join(words)) > max_tokens:  # câu dài bất thường: cắt theo từ, theo đúng phép ước lượng token
            k = max(1, int(max_tokens / 1.3))
            while k > 1 and est_tokens(" ".join(words[:k])) > max_tokens:
                k -= 1
            piece, words = " ".join(words[:k]), words[k:]
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece)
        sent = " ".join(words)
        if cur and est_tokens(cur + " " + sent) > max_tokens:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def toc_nodes(doc: dict[str, Any], max_page: int) -> list[dict[str, Any]]:
    """Cây mục lục -> các nút có điểm bắt đầu"""
    nodes: list[dict[str, Any]] = []
    prev = (0, -1)
    for e in doc["entries"]:
        pg = e.get("pdf_page")
        if pg is None or e.get("out_of_range") or not 1 <= pg <= max_page:
            continue
        line = e["anchor_line"] if e.get("anchored") and e.get("anchor_line") is not None else -1
        start = max((pg, line), prev)
        anchored = bool(e.get("anchored")) and start == (pg, line)
        prev = start
        nodes.append({"id": e["id"], "title": e["title"], "level": e["level"], "kind": e["kind"], "page": start[0],
                      "line": start[1] if anchored else -1, "anchored": anchored, "printed_page": e.get("printed_page"),
                      "suspect": bool(e.get("suspect"))})
    hierarchy.build_tree(nodes)  # cha/đường dẫn tính lại trên các mục còn lại
    for i, n in enumerate(nodes):  # khoảng trang theo mục lục: tới trang của mục kế cùng cấp trở lên
        nxt = next((m["page"] for m in nodes[i + 1:] if m["level"] <= n["level"]), max_page)
        n["page_hint"] = [n["page"], max(n["page"], nxt)]
    return nodes


def _common_prefix(paths: list[list[str]]) -> list[str]:
    out: list[str] = []
    for col in zip(*paths):
        if len(set(col)) != 1:
            break
        out.append(col[0])
    return out


def _items(nodes: list[dict], units: list[tuple[int, int, str]], boundary_level: int) -> tuple[list[list[dict]], int]:
    """Chia chữ cho mục chứa nó rồi gom thành các vùng"""
    by_id = {n["id"]: n for n in nodes}
    starts = [(n["page"], n["line"]) for n in nodes]
    own = {(n["page"], n["line"]) for n in nodes if n["anchored"]}  # dòng tiêu đề đã neo: chính tiêu đề, không phải thân

    def group(n: dict) -> str:
        while n["level"] > boundary_level and n.get("parent_id"):
            n = by_id[n["parent_id"]]
        return n["id"]

    regions: list[list[dict]] = []
    last_group, last_idx, outside = None, None, 0
    for page, line, text in units:
        if (page, line) in own or not text.strip():
            continue
        idx = bisect_right(starts, (page, line)) - 1
        if idx < 0:
            outside += 1
            continue
        node = nodes[idx]
        g = group(node)
        if g != last_group:
            regions.append([])
            last_group = g
        if idx != last_idx:  # vào một mục mới: tiêu đề của nó mở đầu phần chữ của mục
            regions[-1].append({"node": node, "page": page, "text": "#" * (node["level"] + 1) + " " + node["title"], "heading": True})
            last_idx = idx
        regions[-1].append({"node": node, "page": page, "text": text, "heading": False})
    return regions, outside


def _pack(region: list[dict], cfg: ChunkingConfig) -> list[list[dict]]:
    """Cắt một vùng thành các nhóm item vừa `max_tokens` (item quá dài được cắt theo câu)."""
    flat: list[dict] = []
    for it in region:
        if est_tokens(it["text"]) > cfg.max_tokens:
            flat += [{**it, "text": s, "heading": False} for s in split_unit(it["text"], cfg.max_tokens)]
        else:
            flat.append(it)
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for it in flat:
        if cur and est_tokens("\n".join(x["text"] for x in cur + [it])) > cfg.max_tokens:
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    # tiêu đề đứng một mình ở cuối nhóm thì chuyển xuống nhóm sau (tránh chunk chỉ có tiêu đề)
    for i in range(len(groups) - 1):
        while len(groups[i]) > 1 and groups[i][-1]["heading"]:
            groups[i + 1].insert(0, groups[i].pop())
    return [g for g in groups if g]


def build_chunks(nodes: list[dict], units: list[tuple[int, int, str]], cfg: ChunkingConfig, *, document_id: str, document_title: str,
                 printed_offset: int, figures: list[dict] | None = None) -> tuple[list[dict], int]:
    by_id = {n["id"]: n for n in nodes}
    regions, outside = _items(nodes, units, cfg.boundary_level)
    chunks: list[dict] = []
    for region in regions:
        for group in _pack(region, cfg):
            members = list(dict.fromkeys(it["node"]["id"] for it in group))
            first = by_id[members[0]]
            chain: list[dict] = []
            cur: dict | None = first
            while cur is not None:
                chain.append(cur)
                cur = by_id.get(cur["parent_id"]) if cur.get("parent_id") else None
            pick = lambda f: next((n["title"] for n in chain if f(n)), "")  # noqa: E731
            paths = [by_id[m]["path"] for m in members]
            path = _common_prefix(paths) if len(paths) > 1 else paths[0]
            text = "\n".join(it["text"] for it in group)
            pages = [it["page"] for it in group]
            pa, pb = min(pages), max(pages)
            crumb = " > ".join([document_title, *path] if cfg.breadcrumb and document_title else path)
            seq = len(chunks) + 1
            chunks.append({
                "chunk_id": f"{document_id}:c{seq:05d}", "seq": seq, "document_id": document_id, "text": text,
                "context_text": f"{crumb}\n{text}" if crumb else text,
                "part": pick(lambda n: n["kind"] == "part"), "section": pick(lambda n: n["kind"] == "section"),
                "topic": pick(lambda n: n["level"] == 2), "subtopic": pick(lambda n: n["level"] == 3),
                # ảnh theo khoảng trang: chunk trải nhiều trang thì nhận ảnh của mọi trang đó (có thể trùng giữa các chunk)
                "figure_ids": [f["figure_id"] for f in figures or [] if pa <= f["page"] <= pb],
                "toc_path": path, "toc_node_ids": members, "level": first["level"],
                "pages_hint": first["page_hint"],
                # ranh giới chỉ chính xác tới trang khi mục chưa neo được dòng và chunk bắt đầu ở trang của mục đó
                "boundary": not first["anchored"] and pa == first["page"],
                "suspect": any(by_id[m]["suspect"] for m in members),
                "page_start": pa, "page_end": pb, "page_printed_start": pa - printed_offset, "page_printed_end": pb - printed_offset,
                "tokens": est_tokens(text), "chars": len(text),
            })
    return chunks, outside


def _review(chunks: list[dict], cfg: ChunkingConfig) -> list[dict]:
    out = []
    for c in chunks:
        why = []
        if c["tokens"] > cfg.max_tokens * 1.1:
            why.append(f"quá dài (~{round(c['tokens'] / 1.3)} từ)")
        elif c["tokens"] < cfg.min_tokens:
            why.append(f"quá ngắn (~{round(c['tokens'] / 1.3)} từ)")
        if c["boundary"]:
            why.append("vị trí bắt đầu mục chỉ chính xác đến trang")
        if c["suspect"]:
            why.append("mục cần kiểm tra")
        if why:
            out.append({"id": c["chunk_id"], "reason": "; ".join(why), "page": c["page_start"]})
    return out


def run(ctx: StageContext) -> dict:
    files, cfg = ctx.files, ctx.profile.chunking
    rows = [r for r in files.iter_jsonl("pages.jsonl") if not r.get("noise")]
    if not rows:
        raise StageError("Chưa đọc nội dung sách — hãy làm bước Đọc nội dung trước.")
    if not files.exists("toc.auto.json"):
        raise StageError("Chưa có mục lục — hãy làm bước Mục lục trước.")
    ctx.progress(0, 2, "tính lại độ lệch + neo")
    max_page = max(r["page"] for r in rows)
    refresh_toc(ctx, max_page)  # dữ liệu trang có thể mới hơn lần duyệt mục lục
    doc = files.read_json("toc.json")
    off = doc["offset"]
    if off is None:
        raise StageError("Chưa xác định được độ chênh lệch số trang — hãy nhập tay ở bước Mục lục rồi làm lại.")
    skip = set(doc["toc_pages"])
    nodes = toc_nodes(doc, max_page)
    if not nodes:
        raise StageError("Không mục nào của mục lục nằm trong các trang đã đọc — hãy kiểm tra độ chênh lệch số trang.")
    units = [(r["page"], i, ln) for r in rows if r["page"] not in skip for i, ln in enumerate(r["text"].split("\n"))]
    ctx.progress(1, 2, "cắt chunk")
    document_title = ctx.meta().get("title", "")
    figures = files.read_json("figures.json", []) or []
    chunks, outside = build_chunks(nodes, units, cfg, document_id=ctx.document_id, document_title=document_title, printed_offset=off,
                                   figures=figures)
    if not chunks:
        raise StageError("Không tạo được đoạn nào (nội dung sách có thể đang trống).")
    files.write_jsonl("chunks.jsonl", chunks)
    review = _review(chunks, cfg)
    files.write_json("review/chunks.json", review)
    toks = sorted(c["tokens"] for c in chunks)
    summary: dict[str, Any] = {
        "chunks": len(chunks), "tokens": {"min": toks[0], "median": toks[len(toks) // 2], "max": toks[-1]},
        "toc_entries_used": len(nodes), "toc_entries_total": len(doc["entries"]), "offset": off,
        "boundary_chunks": sum(1 for c in chunks if c["boundary"]), "suspect_chunks": sum(1 for c in chunks if c["suspect"]),
        "too_short": sum(1 for c in chunks if c["tokens"] < cfg.min_tokens),
        "too_long": sum(1 for c in chunks if c["tokens"] > cfg.max_tokens * 1.1),
        "outside_toc_lines": outside,
    }
    warnings = []
    if len(nodes) < len(doc["entries"]):
        warnings.append(f"{len(doc['entries']) - len(nodes)} mục của mục lục nằm ngoài các trang đã đọc nên chưa có đoạn nội dung.")
    if outside:
        warnings.append(f"{outside} dòng chữ nằm trước mục đầu tiên của mục lục (bìa, lời nói đầu…) nên không thuộc đoạn nào.")
    if warnings:
        summary["warnings"] = warnings
    return summary
