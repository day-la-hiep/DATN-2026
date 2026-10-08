"""Chạy thẳng chat graph (triage → pre_diagnosis, cấu hình production) để xem LẬP LUẬN của agent, không cần Core / RabbitMQ / UI:

    cd core && uv run python -m agent.test.try_reasoning "Tôi bị nổi mảng đỏ có vảy ở khuỷu tay 2 tuần nay"
    cd core && uv run python -m agent.test.try_reasoning "Da ngứa" --answer "Ở cẳng tay" --answer "Khoảng 1 tuần"
    cd core && uv run python -m agent.test.try_reasoning "..." --no-triage --model deepseek-v4-flash --repeat 3
    cd core && uv run python -m agent.test.try_reasoning "..." --raw --json /tmp/trace.json

In từng bước: mỗi lần `record_reasoning` (dữ kiện, giả thuyết, cờ đỏ, bước tiếp theo), tool tra cứu và kết quả, `ask_user` (tự trả lời bằng
`--answer`, hết thì chọn lựa chọn đầu / "Không rõ"), câu trả lời cuối. Cuối cùng là các check về lập luận (xem `_check`). Exit 1 nếu run
lỗi hoặc có check không đạt. Gọi LLM thật nên kết quả mỗi lần một khác — dùng `--repeat 3` để đánh giá.

Cần Qdrant, Neo4j (không cần Postgres / RabbitMQ / Redis) và `core/.env` có khoá LLM. Conversation id rỗng nên middleware không emit SSE.
Không phải chẩn đoán y khoa — chỉ để kiểm tra luồng lập luận."""
import argparse
import asyncio
import json
import sys
import time
import uuid
import warnings
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `core/` — chạy được cả dạng `python agent/test/try_reasoning.py`

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.middleware.evidence import evidence_status  # noqa: E402
from agent.context.agent_context import AgentContext  # noqa: E402
from agent.tools.reasoning import INVALID_PREFIX, TOOL_NAME as REASONING, render_reasoning, validate_reasoning  # noqa: E402
from app.config.settings import settings  # noqa: E402

_TOOL_BUDGET = 10  # DIAGNOSIS_PROMPT mục 3: tối đa ~10 lần gọi tool mỗi lượt, không tính record_reasoning
_NON_RETRIEVAL = {REASONING, "ask_user", "save_memory"}
_MAX_PAUSES = 5  # số lần dừng ask_user tối đa mỗi run


def _clip(text: object, n: int) -> str:
    s = str(text).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


async def _run(
    question: str,
    model: str,
    answers: list[str],
    on_step: Callable[[dict[str, Any]], None] | None = None,
    on_token: Callable[[str], None] | None = None,
    *,
    graph: Any = None,
    thread_id: str | None = None,
    ask: Callable[[str, list[str]], str] | None = None,
) -> dict[str, Any]:
    """`on_step` được gọi NGAY khi mỗi bước xong (để CLI in dần thay vì đợi hết lượt), `on_token` với từng đoạn chữ model đang sinh.
    Chat nhiều lượt: truyền cùng `graph` (đã có checkpointer) + `thread_id` cho mọi lượt; `ask(câu hỏi, lựa chọn)` trả lời `ask_user`
    thay cho `answers` (người dùng gõ tay)."""
    from agent.graph.chat_graph import build_agent_graph, config_for  # import muộn: `--no-triage` phải đặt settings trước khi dựng graph

    graph = graph or build_agent_graph()
    ctx = AgentContext(user_id="try-user", conversation_id="", message_id="try", model=model)
    cfg = config_for(thread_id or f"try-{uuid.uuid4()}")
    input_: object = {"messages": [HumanMessage(content=question)]}
    messages: list[AnyMessage] = []
    steps: list[dict[str, Any]] = []
    error: str | None = None
    started = time.perf_counter()
    streamed = False  # đã có token stream ra từ bước model hiện tại -> chữ của bước đó đã hiện rồi, khỏi in lại

    def add_step(step: dict[str, Any]) -> None:
        nonlocal streamed
        if step["kind"] == "model":
            step["streamed"] = streamed and bool(step["text"].strip())
            streamed = False
        steps.append(step)
        if on_step:
            on_step(step)

    try:
        for pause in range(_MAX_PAUSES + 1):
            interrupt = None
            async for mode, chunk in graph.astream(input_, config=cfg, context=ctx, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    # token model chính do node `pre_diagnosis` chuyển tiếp (giống `turn.py`)
                    if isinstance(chunk, dict) and chunk.get("type") == "token" and chunk.get("text"):
                        streamed = True
                        if on_token:
                            on_token(chunk["text"])
                    continue
                node_updates = cast("dict[str, Any]", chunk)
                if "__interrupt__" in node_updates:
                    interrupt = node_updates["__interrupt__"][0]
                    break
                for update in node_updates.values():
                    for m in update.get("messages", []) if isinstance(update, dict) else []:
                        if isinstance(m, AIMessage):
                            messages.append(m)
                            add_step({"kind": "model", "text": m.text, "calls": [{"name": c["name"], "args": c["args"]} for c in m.tool_calls]})
                        elif isinstance(m, ToolMessage):
                            messages.append(m)
                            add_step({"kind": "tool", "name": m.name or "?", "content": str(m.content), "error": m.status == "error"})
            if interrupt is None:
                break
            value = interrupt.value if isinstance(interrupt.value, dict) else {}
            options = value.get("options") or []
            if ask:
                answer = ask(str(value.get("question", "")), options)
            else:
                answer = answers[pause] if pause < len(answers) else (options[0] if options else "Không rõ")
            add_step({"kind": "ask_user", "question": value.get("question", ""), "options": options, "answer": answer})
            messages.append(ToolMessage(content=answer, name="ask_user", tool_call_id=f"ask-{pause}"))
            input_ = Command(resume=answer)
    except GraphRecursionError:
        error = "GraphRecursionError (vượt recursion_limit)"
    except Exception as exc:  # noqa: BLE001 — in lỗi thay vì dừng cả loạt `--repeat`
        error = f"{type(exc).__name__}: {exc}"
    return {"steps": steps, "messages": messages, "error": error, "seconds": round(time.perf_counter() - started, 1)}


def _reasoning_calls(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c["args"] for s in steps if s["kind"] == "model" for c in s["calls"] if c["name"] == REASONING]


def _check(steps: list[dict[str, Any]], messages: list[AnyMessage]) -> dict[str, bool]:
    """Các check về lập luận (DIAGNOSIS_PROMPT mục 1, 3.0). Lượt không gọi tool nào (chào hỏi, ngoài phạm vi, triage trả lời) -> bỏ qua."""
    calls = [c for s in steps if s["kind"] == "model" for c in s["calls"]]
    if not calls:
        return {}
    retrieval = [c["name"] for c in calls if c["name"] not in _NON_RETRIEVAL]
    checks: dict[str, bool] = {
        # §3.0: record_reasoning(stage=initial) phải là lời gọi tool ĐẦU TIÊN
        "initial_first": calls[0]["name"] == REASONING and calls[0]["args"].get("stage") == "initial",
        "budget": len(retrieval) <= _TOOL_BUDGET,
        # chữ viết cùng bước với `ask_user` bị stream ra FE rồi mất khi lượt tạm dừng
        "no_text_with_ask_user": not any(s["kind"] == "model" and s["text"].strip() and any(c["name"] == "ask_user" for c in s["calls"]) for s in steps),
        # không được để `record_reasoning` bị middleware từ chối mà không sửa lại (lời từ chối mở đầu bằng INVALID_PREFIX)
        "reasoning_not_rejected": not any(s["kind"] == "tool" and s["name"] == REASONING and s["content"].startswith(INVALID_PREFIX) for s in steps),
    }
    if retrieval:
        # sau tra cứu phải có lập luận cập nhật (after_evidence / final) trước câu trả lời cuối
        later = [a.get("stage") for a in _reasoning_calls(steps)[1:]]
        checks["reasoned_after_evidence"] = any(st in ("after_evidence", "final") for st in later)
        # không có bằng chứng (sách / web) thì giả thuyết cuối phải rỗng (mục 1)
        if evidence_status(messages) == "none":
            last = _reasoning_calls(steps)[-1] if _reasoning_calls(steps) else {}
            checks["no_hypothesis_without_evidence"] = not last.get("hypotheses")
    return checks


def _print_step(i: int, s: dict[str, Any], raw: bool) -> None:
    if s["kind"] == "model":
        for c in s["calls"]:
            if c["name"] == REASONING:
                data, problems = validate_reasoning(c["args"])
                print(f"[{i}] model → record_reasoning (stage={c['args'].get('stage')})")
                body = render_reasoning(data) if data else "(tham số không hợp lệ) " + "; ".join(problems)
                print("      " + body.replace("\n", "\n      "))
            else:
                print(f"[{i}] model → {c['name']}({_clip(json.dumps(c['args'], ensure_ascii=False), 150)})")
        if not s["calls"]:
            # chữ đã stream ra màn hình từng token rồi -> chỉ in dòng tiêu đề, không lặp lại cả đoạn
            print(f"[{i}] model → trả lời" + (" (đã stream ở trên)" if s.get("streamed") else ":\n      " + s["text"].strip().replace("\n", "\n      ")))
        elif s["text"].strip() and not s.get("streamed"):
            print(f"      (kèm chữ: {_clip(s['text'], 120)})")
    elif s["kind"] == "tool":
        mark = " !LỖI" if s["error"] or s["content"].startswith(INVALID_PREFIX) else ""
        print(f"[{i}] tool  {s['name']}{mark}: " + (s["content"] if raw else _clip(s["content"], 160)))
    else:
        print(f"[{i}] ask_user: {_clip(s['question'], 100)}  {s['options']}  → tự trả lời '{s['answer']}'")


class LivePrinter:
    """In dần từng bước + token ngay khi chúng xảy ra; dùng chung cho `main` và chat trong TUI."""

    def __init__(self, raw: bool = False) -> None:
        self.raw, self.i, self.tokens = raw, 0, False

    def token(self, text: str) -> None:
        if not self.tokens:
            print("      ", end="")
            self.tokens = True
        print(text.replace("\n", "\n      "), end="", flush=True)

    def step(self, step: dict[str, Any]) -> None:
        self.end_tokens()
        self.i += 1
        _print_step(self.i, step, self.raw)
        sys.stdout.flush()

    def end_tokens(self) -> None:
        if self.tokens:  # kết thúc dòng đang stream trước khi in bước
            print()
            self.tokens = False


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="tin nhắn người dùng")
    parser.add_argument("--model", help="id ngắn trong AGENT_MODEL_CHOICES hoặc 'provider:model'; mặc định settings.AGENT_MODEL")
    parser.add_argument("--answer", action="append", default=[], help="câu trả lời cho các lần ask_user, theo thứ tự (lặp lại được)")
    parser.add_argument("--no-triage", action="store_true", help="bỏ bước lọc intent để ép vào graph tiền chẩn đoán")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--raw", action="store_true", help="in đủ kết quả tool, không cắt")
    parser.add_argument("--json", metavar="FILE", help="lưu trace (steps + checks) ra file JSON")
    args = parser.parse_args()

    if args.no_triage:
        settings.AGENT_TRIAGE_ENABLED = False
    model = args.model or ""
    if model and ":" not in model:
        model = settings.AGENT_MODEL_CHOICES[model]

    runs: list[dict[str, Any]] = []
    for n in range(1, args.repeat + 1):
        print(f"\n===== run {n}/{args.repeat} =====", flush=True)
        printer = LivePrinter(args.raw)
        result = await _run(args.question, model, args.answer, printer.step, printer.token)
        printer.end_tokens()
        checks = _check(result["steps"], result["messages"])
        ok = result["error"] is None and all(checks.values())
        print(f"----- run {n}/{args.repeat}  {result['seconds']}s  {'OK' if ok else 'FAIL'} -----")
        if result["error"]:
            print("ERROR:", result["error"])
        print("checks:", {k: ("ok" if v else "FAIL") for k, v in checks.items()} or "(không gọi tool — bỏ qua)")
        stages = [a.get("stage") for a in _reasoning_calls(result["steps"])]
        tools = [c["name"] for s in result["steps"] if s["kind"] == "model" for c in s["calls"]]
        print("chuỗi tool:", " → ".join(tools) or "(không)", "| stage lập luận:", stages or "-")
        runs.append({"ok": ok, "error": result["error"], "seconds": result["seconds"], "checks": checks, "steps": result["steps"]})

    print(f"\n{sum(r['ok'] for r in runs)}/{len(runs)} run đạt")
    if args.json:
        Path(args.json).write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        print("trace →", args.json)
    sys.exit(0 if all(r["ok"] for r in runs) else 1)


if __name__ == "__main__":
    asyncio.run(main())
