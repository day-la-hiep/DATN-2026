"""CLI nhanh với các câu hỏi quen thuộc — gọi lại `try_retrieval` (tra cứu) và `try_reasoning` (graph lập luận):

    cd core && uv run python -m agent.test.quick                 # liệt kê preset
    cd core && uv run python -m agent.test.quick r 1             # tra cứu preset #1 (cả 4 tool)   (r = retrieve)
    cd core && uv run python -m agent.test.quick r 2 -t keyword  # tham số thừa chuyển thẳng cho try_retrieval
    cd core && uv run python -m agent.test.quick g 1             # lập luận preset #1              (g = graph)
    cd core && uv run python -m agent.test.quick g 3 --repeat 3  # tham số thừa chuyển thẳng cho try_reasoning
    cd core && uv run python -m agent.test.quick r "câu tuỳ ý"   # không phải số thì coi là câu hỏi mới
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `core/`

# Sách trong kho là tiếng Anh nên câu tra cứu dùng từ khoá Anh cho nhánh BM25; câu tiếng Việt dành cho semantic / lập luận.
RETRIEVE = [
    "psoriasis plaque treatment",
    "methotrexate contraindication",
    "mảng đỏ có vảy bạc ở khuỷu tay",
    "tiêu chí phân biệt vảy nến và chàm",
    "melanoma red flag ABCDE",
    "thuốc bôi corticoid tác dụng phụ",
]

# (câu hỏi, các câu trả lời cho ask_user, cờ thêm)
REASON = [
    ("Tôi bị nổi mảng đỏ có vảy trắng ở khuỷu tay khoảng 2 tuần, hơi ngứa", [], ["--no-triage"]),
    ("Da tôi bị ngứa và nổi mẩn", ["Ở cẳng tay", "Khoảng 1 tuần"], ["--no-triage"]),
    ("Nốt ruồi ở lưng tôi mới to ra và hơi chảy máu", [], ["--no-triage"]),
    ("Methotrexate có chống chỉ định gì không?", [], ["--no-triage"]),
    ("Chào bạn", [], []),  # triage trả lời thẳng, không vào graph lập luận
]


def _list() -> None:
    print("Tra cứu (r):")
    for i, q in enumerate(RETRIEVE, 1):
        print(f"  r {i}  {q}")
    print("Graph lập luận (g):")
    for i, (q, answers, _) in enumerate(REASON, 1):
        print(f"  g {i}  {q}" + (f"   (ask_user → {answers})" if answers else ""))


def _pick(items: list, arg: str):
    return items[int(arg) - 1] if arg.isdigit() and 1 <= int(arg) <= len(items) else None


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("r", "g"):
        _list()
        return
    mode, what, extra = argv[0], argv[1], argv[2:]
    if mode == "r":
        from agent.test import try_retrieval as module

        query = _pick(RETRIEVE, what) or what
        sys.argv = ["try_retrieval", query, *extra]
    else:
        from agent.test import try_reasoning as module

        preset = _pick(REASON, what)
        question, answers, flags = preset if preset else (what, [], ["--no-triage"])
        sys.argv = ["try_reasoning", question, *flags, *(a for ans in answers for a in ("--answer", ans)), *extra]
    asyncio.run(module.main())


if __name__ == "__main__":
    main()
