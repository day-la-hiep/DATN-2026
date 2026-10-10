#!/usr/bin/env python3
"""Thử nghiệm luồng lập luận của agent bằng cách gọi THẲNG graph (không API/RabbitMQ/Postgres).

Chạy từ core/:  uv run python .claude/skills/experiment-agent-flow/experiment.py --help

  # 1 câu hỏi, cấu hình mặc định
  experiment.py "Bệnh chàm là gì?"
  # đổi model / thêm chỉ dẫn vào prompt / giới hạn tool / bỏ middleware
  experiment.py "..." --model deepseek-v4-flash --prompt-append "Luôn hỏi lại trước khi kết luận." \
      --tools record_reasoning,ask_user,hybrid_retrieval --skip-middleware inject_long_term_memory
  # nhiều câu hỏi x nhiều biến thể x lặp lại, lưu trace JSON
  experiment.py --cases examples/cases.json --variants examples/variants.json --repeat 2 --out /tmp/exp

Mỗi lần chạy in trace (model gọi tool gì -> tool trả gì -> câu trả lời) và cuối cùng là bảng so sánh
chuỗi tool giữa các biến thể. `ask_user` được tự trả lời (--answer hoặc lựa chọn đầu tiên).
Exit code 1 nếu có run lỗi hoặc không đạt check (expect_tools/forbid_tools/plan_first/budget).
"""
import argparse, asyncio, json, sys, time, uuid, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.cwd()))  # chạy từ core/ để import `agent`, `app`

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent.graph.chat_graph import (  # noqa: E402
    ALL_TOOLS, build_agent_graph, config_for, default_middleware,
)
from agent.prompt.orchestrator import SYSTEM_PROMPT  # noqa: E402
from agent.context.agent_context import AgentContext  # noqa: E402
from app.config.settings import settings  # noqa: E402

TOOL_BUDGET = 8  # SYSTEM_PROMPT mục 3: tối đa ~8 lần gọi tool/lượt (kể cả make_plan)
ERR_PREFIX = "Lỗi khi gọi công cụ"  # agent/middleware/tool.py biến lỗi tool thành ToolMessage này


def resolve_model(m: str | None) -> str:
    if not m:
        return ""
    return m if ":" in m else settings.AGENT_MODEL_CHOICES[m]


def make_graph(v: dict):
    prompt = SYSTEM_PROMPT
    if v.get("system_prompt_file"):
        prompt = Path(v["system_prompt_file"]).read_text()
    if v.get("prompt_append"):
        prompt = prompt + "\n\n" + v["prompt_append"]
    tools = ALL_TOOLS
    if v.get("tools"):
        names = {t.name: t for t in ALL_TOOLS}
        unknown = [n for n in v["tools"] if n not in names]
        if unknown:
            sys.exit(f"tool không tồn tại: {unknown}. Có: {list(names)}")
        tools = [names[n] for n in v["tools"]]
    mw = [m for m in default_middleware() if m.name not in set(v.get("skip_middleware", []))]
    return build_agent_graph(tools=list(tools), system_prompt=prompt, middleware=mw)


def _clip(s, n):
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


async def run_one(graph, variant, case, answers, quiet):
    ctx = AgentContext(  # conversation_id rỗng => middleware KHÔNG emit Redis/SSE
        user_id="exp-user", conversation_id="", message_id="exp",
        model=resolve_model(variant.get("model")),
    )
    cfg = config_for(f"exp-{uuid.uuid4()}")
    input_: object = {"messages": [HumanMessage(content=case["question"])]}
    steps, err, answered = [], None, 0
    t0 = time.time()
    try:
        for _ in range(6):  # tối đa 5 lần dừng ask_user
            interrupt = None
            async for chunk in graph.astream(input_, config=cfg, context=ctx, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupt = chunk["__interrupt__"][0]
                    break
                for upd in chunk.values():
                    if not isinstance(upd, dict):
                        continue
                    for m in upd.get("messages", []):
                        if isinstance(m, AIMessage):
                            u = m.usage_metadata or {}
                            steps.append({"kind": "model", "text": m.text,
                                          "tool_calls": [{"name": c["name"], "args": c["args"]} for c in m.tool_calls],
                                          "in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0)})
                        elif isinstance(m, ToolMessage):
                            c = str(m.content)
                            steps.append({"kind": "tool", "name": m.name, "content": c,
                                          "error": c.startswith(ERR_PREFIX) or m.status == "error"})
            if interrupt is None:
                break
            val = interrupt.value if isinstance(interrupt.value, dict) else {}
            opts = val.get("options") or []
            if answered < len(answers):
                ans = answers[answered]
            else:
                ans = opts[0] if opts else "Không rõ"
            answered += 1
            steps.append({"kind": "ask_user", "question": val.get("question", ""), "options": opts, "answer": ans})
            input_ = Command(resume=ans)
    except GraphRecursionError:
        err = "GraphRecursionError (vượt recursion_limit)"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    secs = time.time() - t0

    calls = [c["name"] for s in steps if s["kind"] == "model" for c in s["tool_calls"]]
    final = next((s["text"] for s in reversed(steps) if s["kind"] == "model" and not s["tool_calls"]), "")
    checks = {}
    if "expect_tools" in case:
        checks["expect_tools"] = all(t in calls for t in case["expect_tools"])
    if "forbid_tools" in case:
        checks["forbid_tools"] = not any(t in calls for t in case["forbid_tools"])
    # chữ sinh ra CÙNG bước với lời gọi ask_user bị stream ra FE rồi mất khi turn tạm dừng
    checks["no_text_with_ask_user"] = not any(
        s["kind"] == "model" and s["text"].strip() and any(c["name"] == "ask_user" for c in s["tool_calls"])
        for s in steps)
    checks["plan_first"] = (calls[:1] == ["make_plan"]) if calls else True
    checks["budget"] = len(calls) <= TOOL_BUDGET
    res = {
        "case": case["id"], "variant": variant["name"], "seconds": round(secs, 1), "error": err,
        "tool_seq": calls, "model_calls": sum(s["kind"] == "model" for s in steps),
        "tool_errors": sum(1 for s in steps if s["kind"] == "tool" and s["error"]),
        "tokens_in": sum(s.get("in", 0) for s in steps if s["kind"] == "model"),
        "tokens_out": sum(s.get("out", 0) for s in steps if s["kind"] == "model"),
        "checks": checks, "answer": final, "steps": steps,
    }
    res["ok"] = err is None and all(checks.values())
    if not quiet:
        print_trace(res)
    return res


def print_trace(r):
    print(f"\n=== {r['case']} | {r['variant']} | {r['seconds']}s | {'OK' if r['ok'] else 'FAIL'} ===")
    for i, s in enumerate(r["steps"], 1):
        if s["kind"] == "model":
            if s["tool_calls"]:
                calls = ", ".join(f"{c['name']}({_clip(json.dumps(c['args'], ensure_ascii=False), 110)})" for c in s["tool_calls"])
                print(f"[{i}] model -> {calls}")
            else:
                print(f"[{i}] model -> trả lời ({len(s['text'])} ký tự)")
        elif s["kind"] == "tool":
            print(f"[{i}] tool  {s['name']}{' !LỖI' if s['error'] else ''}: {_clip(s['content'], 130)}")
        else:
            print(f"[{i}] ask_user: {_clip(s['question'], 80)} {s['options']} -> auto '{s['answer']}'")
    if r["error"]:
        print("ERROR:", r["error"])
    print("checks:", {k: ("ok" if v else "FAIL") for k, v in r["checks"].items()},
          f"| model_calls={r['model_calls']} tool_errors={r['tool_errors']} tokens={r['tokens_in']}/{r['tokens_out']}")
    print("ANSWER:", _clip(r["answer"], 400))


def summary(results):
    print("\n##### SO SÁNH CHUỖI TOOL #####")
    for case in dict.fromkeys(r["case"] for r in results):
        print(f"\n{case}")
        for r in (x for x in results if x["case"] == case):
            seq = " → ".join(r["tool_seq"]) or "(không gọi tool)"
            print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['variant']:<18} {r['seconds']:>5}s  {seq}")
    n_ok = sum(r["ok"] for r in results)
    print(f"\n{n_ok}/{len(results)} run đạt")


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?")
    ap.add_argument("--cases"); ap.add_argument("--variants")
    ap.add_argument("--model"); ap.add_argument("--system-prompt-file"); ap.add_argument("--prompt-append")
    ap.add_argument("--tools", help="danh sách tool, cách nhau bằng dấu phẩy (mặc định: tất cả)")
    ap.add_argument("--skip-middleware", default="", help="vd inject_long_term_memory,select_model")
    ap.add_argument("--answer", action="append", default=[], help="câu trả lời cho ask_user (lặp lại được)")
    ap.add_argument("--repeat", type=int, default=1); ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--out"); ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if a.cases:
        cases = json.loads(Path(a.cases).read_text())
    elif a.question:
        cases = [{"id": "q1", "question": a.question}]
    else:
        ap.error("cần câu hỏi hoặc --cases")
    if a.variants:
        variants = json.loads(Path(a.variants).read_text())
        variants = [{"name": k, **v} for k, v in variants.items()]
    else:
        variants = [{"name": "default", "model": a.model, "system_prompt_file": a.system_prompt_file,
                     "prompt_append": a.prompt_append, "tools": a.tools.split(",") if a.tools else None,
                     "skip_middleware": [x for x in a.skip_middleware.split(",") if x]}]
    graphs = {v["name"]: make_graph(v) for v in variants}

    jobs = [(v, c, r) for c in cases for v in variants for r in range(a.repeat)]
    sem = asyncio.Semaphore(a.parallel)

    async def job(v, c, r):
        async with sem:
            res = await run_one(graphs[v["name"]], v, c, c.get("answers", a.answer), a.quiet or a.parallel > 1)
            res["repeat"] = r
            return res

    results = await asyncio.gather(*(job(*j) for j in jobs))
    if a.parallel > 1 and not a.quiet:
        for r in results:
            print_trace(r)
    summary(results)
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        for r in results:
            (out / f"{r['case']}__{r['variant']}__{r['repeat']}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2))
        print(f"trace JSON -> {out}/")
    sys.exit(0 if all(r["ok"] for r in results) else 1)


asyncio.run(main())
