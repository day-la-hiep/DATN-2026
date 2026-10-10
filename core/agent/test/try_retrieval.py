"""Gọi thẳng các tool tra cứu của agent để xem response, không cần chạy Core / worker / UI:

    cd core && uv run python -m agent.test.try_retrieval "vảy nến mảng khuỷu tay"                # cả 4 tool
    cd core && uv run python -m agent.test.try_retrieval "methotrexate" -t keyword -t kg -k 3    # chọn tool, top_k
    cd core && uv run python -m agent.test.try_retrieval "psoriasis" -t hybrid --raw             # JSON nguyên văn
    cd core && uv run python -m agent.test.try_retrieval --stats                                 # kho đang có gì

Cần Qdrant (và Neo4j cho `kg` / `hybrid`) đang chạy, đọc `core/.env`. Model embedding / reranker tải local ở lần đầu nên chậm."""
import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `core/` — chạy được cả dạng `python agent/test/try_retrieval.py`

from agent.tools.hybrid_retrieval import hybrid_retrieval, keyword_search, knowledge_graph_search, semantic_search  # noqa: E402
from app.api.deps import get_knowledge_base_service  # noqa: E402

TOOLS = {
    "hybrid": hybrid_retrieval,
    "semantic": semantic_search,
    "keyword": keyword_search,
    "kg": knowledge_graph_search,
}


def _show(name: str, raw: str, seconds: float, full: bool) -> None:
    data = json.loads(raw)
    results = data.get("results", [])
    print(f"\n=== {name}  ({seconds:.2f}s)  evidence_found={data.get('evidence_found')}  ranked_by={data.get('ranked_by')}  kết quả={len(results)}")
    for r in results:
        text = str(r.get("text", "")).replace("\n", " ")
        where = f"{r.get('title', '')} | {r.get('section', '')} | {r.get('pages', '')}" if r["source"] == "book" else r.get("title", "")
        print(f"  #{r['rank']} [{r['source']}] score={r.get('score', '-')}  {where}")
        print(f"      {text if full else text[:220] + ('…' if len(text) > 220 else '')}")
    for note in data.get("notes", []):
        print(f"  ! {note}")


async def _stats() -> None:
    kb = get_knowledge_base_service()
    records = await kb.all_document_chunks()
    print(f"Tổng chunk (mọi collection): {len(records)}")
    for title, n in Counter(str((r.payload or {}).get("document_title")) for r in records).most_common():
        print(f"  {n:5d}  {title}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="câu hỏi / từ khoá cần tra")
    parser.add_argument("-t", "--tool", action="append", choices=[*TOOLS], help="tool cần gọi (lặp lại được); mặc định: cả 4")
    parser.add_argument("-k", "--top-k", type=int, default=5)
    parser.add_argument("--full", action="store_true", help="in đủ nội dung đoạn, không cắt 220 ký tự")
    parser.add_argument("--raw", action="store_true", help="in JSON nguyên văn tool trả về cho model")
    parser.add_argument("--stats", action="store_true", help="liệt kê số chunk theo sách trong Qdrant rồi thoát")
    args = parser.parse_args()

    if args.stats:
        await _stats()
        return
    if not args.query:
        parser.error("thiếu query (hoặc dùng --stats)")

    for name in args.tool or list(TOOLS):
        start = time.perf_counter()
        raw: str = await TOOLS[name].ainvoke({"query": args.query, "top_k": args.top_k})
        seconds = time.perf_counter() - start
        if args.raw:
            print(f"\n=== {name}  ({seconds:.2f}s)\n{raw}")
        else:
            _show(name, raw, seconds, args.full)


if __name__ == "__main__":
    asyncio.run(main())
