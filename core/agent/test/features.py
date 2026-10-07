"""Khai báo các chức năng có thể thử trong TUI (`agent/test/cli.py`). Thêm chức năng mới = viết một hàm `async def run(text, cfg, preset)`
rồi đăng ký bằng `FEATURES.append(Feature(...))` ở cuối file; khung CLI tự có menu, preset, cài đặt (`/set`) và xử lý Ctrl+C.

`run` nhận: `text` — câu người dùng gõ (hoặc nội dung preset), `cfg` — giá trị hiện tại của các `Setting`, `preset` — `Preset` đang chọn (None
nếu gõ tự do). Module nặng (model, Qdrant, Neo4j) import MUỘN trong `run` để mở menu nhanh."""
import json
import sys
from collections import Counter
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from agent.test.quick import REASON, RETRIEVE


@dataclass
class Setting:
    name: str
    default: Any  # kiểu của default quyết định cách parse: bool ("on"/"off"), int, hoặc str
    help: str
    choices: list[str] | None = None


@dataclass
class Preset:
    label: str
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # ghi đè cài đặt chỉ cho preset này (vd câu trả lời ask_user)


@dataclass
class Feature:
    key: str
    title: str
    help: str
    run: Callable[[str, dict[str, Any], Preset | None], Coroutine[Any, Any, None]]
    settings: list[Setting] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)
    needs_input: bool = True  # False: chức năng không cần câu hỏi (vd thống kê), Enter trống là chạy
    commands: dict[str, tuple[str, Callable[[], None]]] = field(default_factory=dict)  # lệnh /riêng của chức năng: tên -> (mô tả, hàm)


async def _run_main(module: Any, argv: list[str]) -> None:
    """Các script `try_*` đọc `sys.argv` và có thể `sys.exit` sau mỗi lần chạy — ở đây chỉ cần quay lại prompt."""
    sys.argv = argv
    try:
        await module.main()
    except SystemExit:
        pass


async def _retrieval(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from agent.test import try_retrieval

    tools = [t.strip() for t in str(cfg["tools"]).split(",") if t.strip() and t.strip() != "all"]
    argv = ["try_retrieval", text, "-k", str(cfg["top_k"]), *(a for t in tools for a in ("-t", t))]
    argv += [flag for flag, on in (("--full", cfg["full"]), ("--raw", cfg["raw"])) if on]
    await _run_main(try_retrieval, argv)


async def _reasoning(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from agent.test import try_reasoning

    answers = [a.strip() for a in str(preset.extra.get("answers") if preset and "answers" in preset.extra else cfg["answers"]).split("|") if a.strip()]
    argv = ["try_reasoning", text, "--repeat", str(cfg["repeat"]), *(a for ans in answers for a in ("--answer", ans))]
    if not cfg["triage"]:
        argv.append("--no-triage")
    if cfg["model"]:
        argv += ["--model", str(cfg["model"])]
    if cfg["raw"]:
        argv.append("--raw")
    await _run_main(try_reasoning, argv)


_CHAT: dict[str, Any] = {"graph": None, "thread": "", "turns": 0}


def _chat_reset() -> None:
    _CHAT.update(graph=None, thread="", turns=0)
    print("Đã mở hội thoại mới.")


def _ask_user(question: str, options: list[str]) -> str:
    """Agent dùng `ask_user` để hỏi lại — người dùng gõ số (chọn lựa chọn) hoặc gõ câu trả lời; Enter trống = lựa chọn đầu / "Không rõ"."""
    from agent.test import ui

    print(f"\n[agent hỏi] {question}")
    if not options:
        return ui.ask("   bạn trả lời> ") or "Không rõ"
    other = object()
    picked = ui.pick("   Chọn câu trả lời:", [*((o, o) for o in options), (other, "Khác — tự nhập...")])
    return ui.ask("   bạn trả lời> ") or "Không rõ" if picked is other else picked


async def _chat(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    """Hội thoại nhiều lượt: cùng một graph + `thread_id` nên checkpointer nối tiếp tin nhắn, agent nhớ các lượt trước (giống chat thật)."""
    from agent.test import try_reasoning
    from app.config.settings import settings

    if _CHAT["graph"] is None:
        settings.AGENT_TRIAGE_ENABLED = bool(cfg["triage"])  # phải đặt TRƯỚC khi dựng graph; đổi /set triage có hiệu lực từ hội thoại mới
        from agent.graph.chat_graph import build_agent_graph
        import uuid

        _CHAT.update(graph=build_agent_graph(), thread=f"chat-{uuid.uuid4()}", turns=0)
    model = str(cfg["model"])
    if model and ":" not in model:
        model = settings.AGENT_MODEL_CHOICES[model]
    _CHAT["turns"] += 1
    print(f"[lượt {_CHAT['turns']} · thread {_CHAT['thread'][-8:]}]")
    printer = try_reasoning.LivePrinter(bool(cfg["raw"]))
    try:
        result = await try_reasoning._run(
            text, model, [], printer.step, printer.token, graph=_CHAT["graph"], thread_id=_CHAT["thread"], ask=_ask_user
        )
    except BaseException:
        # Bị ngắt giữa chừng (Ctrl+C) có thể để lại `tool_calls` chưa có kết quả trong checkpoint -> lượt sau LLM từ chối cứng; mở hội thoại mới cho an toàn.
        _chat_reset()
        raise
    printer.end_tokens()
    if result["error"]:
        print("ERROR:", result["error"])
        _chat_reset()  # lỗi giữa lượt cũng có thể để lại trạng thái dở


async def _kb_stats(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_base_service

    records = await get_knowledge_base_service().all_document_chunks()
    print(f"Tổng chunk (mọi collection): {len(records)}")
    for title, n in Counter(str((r.payload or {}).get("document_title")) for r in records).most_common():
        print(f"  {n:5d}  {title}")


async def _dermo(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_graph_service

    rows = await get_knowledge_graph_service().search_dermo_terms(text, limit=int(cfg["limit"]))
    if not rows:
        print("(không có term nào khớp)")
    for r in rows:
        print(f"- {r['id']}  {r['name']}")
        print(f"    cha: {', '.join(r['parents']) or '-'}  |  synonyms: {', '.join((r['synonyms'] or [])[:5]) or '-'}")
        if r["related"] and r["related"][0].get("name"):
            print("    liên quan: " + json.dumps(r["related"][:5], ensure_ascii=False))


async def _kg_seeds(text: str, cfg: dict[str, Any], preset: Preset | None) -> None:
    from app.api.deps import get_knowledge_graph_service

    entities = [e.strip() for e in text.split(",") if e.strip()]
    seeds, unmatched, dermo_ids = await get_knowledge_graph_service().resolve_seeds(entities)
    print(f"DermO id: {sorted(dermo_ids) or '-'}")
    print(f"Khớp nút PrimeKG ({len(seeds)}):")
    for s in seeds:
        print(f"  [{s['type']}] {s['name']}")
    if unmatched:
        print(f"Không khớp: {unmatched}")


FEATURES: list[Feature] = [
    Feature(
        key="retrieval",
        title="Tra cứu (hybrid / semantic / keyword / kg)",
        help="Gọi thẳng các tool tra cứu để xem kết quả xếp hạng. Cần Qdrant (+ Neo4j cho kg/hybrid).",
        run=_retrieval,
        settings=[
            Setting("tools", "all", "tool cần gọi, cách nhau dấu phẩy: hybrid,semantic,keyword,kg hoặc all"),
            Setting("top_k", 5, "số kết quả mỗi tool"),
            Setting("full", False, "in đủ nội dung đoạn"),
            Setting("raw", False, "in JSON nguyên văn tool trả về"),
        ],
        presets=[Preset(q, q) for q in RETRIEVE],
    ),
    Feature(
        key="reasoning",
        title="Graph lập luận (triage → pre_diagnosis)",
        help="Chạy chat graph với LLM thật, in từng bước lập luận + các check. Cần Qdrant, Neo4j và khoá LLM.",
        run=_reasoning,
        settings=[
            Setting("triage", False, "bật bước lọc intent (tắt = ép vào graph tiền chẩn đoán)"),
            Setting("model", "", "id ngắn trong AGENT_MODEL_CHOICES hoặc provider:model; rỗng = mặc định"),
            Setting("answers", "", "câu trả lời cho ask_user, cách nhau dấu |"),
            Setting("repeat", 1, "số lần chạy lại để đánh giá độ ổn định"),
            Setting("raw", False, "in đủ kết quả tool, không cắt"),
        ],
        presets=[Preset(q + (f"   (ask_user → {a})" if a else ""), q, {"answers": " | ".join(a)} if a else {}) for q, a, _ in REASON],
    ),
    Feature(
        key="chat",
        title="Chat nhiều lượt với agent",
        help="Hội thoại liên tục như app thật: agent nhớ các lượt trước, hỏi lại bằng ask_user thì bạn trả lời trực tiếp. /new để bắt đầu hội thoại mới.",
        run=_chat,
        settings=[
            Setting("triage", True, "bật bước lọc intent (đổi có hiệu lực từ hội thoại mới)"),
            Setting("model", "", "id ngắn trong AGENT_MODEL_CHOICES hoặc provider:model; rỗng = mặc định"),
            Setting("raw", False, "in đủ kết quả tool, không cắt"),
        ],
        presets=[Preset(t, t) for t in ("Chào bạn", "Da tôi bị ngứa và nổi mẩn", "Tôi bị nổi mảng đỏ có vảy trắng ở khuỷu tay khoảng 2 tuần")],
        commands={"new": ("bắt đầu hội thoại mới (quên các lượt trước)", _chat_reset)},
    ),
    Feature(
        key="kb_stats",
        title="Thống kê kho Qdrant",
        help="Số chunk theo từng sách trong kho tri thức.",
        run=_kb_stats,
        needs_input=False,
    ),
    Feature(
        key="dermo",
        title="Tra thuật ngữ DermO (Neo4j)",
        help="`search_dermo_terms`: tìm term theo tên / synonym, kèm term cha và quan hệ.",
        run=_dermo,
        settings=[Setting("limit", 5, "số term tối đa")],
        presets=[Preset(t, t) for t in ("psoriasis", "atopic dermatitis", "acne", "melanoma")],
    ),
    Feature(
        key="kg_seeds",
        title="Khớp thực thể PrimeKG",
        help="`resolve_seeds`: tên bệnh/triệu chứng (cách nhau dấu phẩy) → nút PrimeKG khớp + DermO id.",
        run=_kg_seeds,
        presets=[Preset(t, t) for t in ("psoriasis", "atopic dermatitis, pruritus", "methotrexate")],
    ),
]
