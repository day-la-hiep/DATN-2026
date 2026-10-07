---
name: experiment-agent-flow
description: Experiment with, compare and debug the Derma agent's reasoning flow (which tools it calls, in what order, how it plans, when it asks the user) by running the LangGraph agent directly with variants of model, system prompt, tool set and middleware — no API, RabbitMQ or Postgres needed. Use when asked to try a prompt change, A/B test models or prompts, see the tool-call trace, check whether the agent follows the SYSTEM_PROMPT rules (plan first, tool budget), count tool calls/tokens, or evaluate a new tool/middleware on sample questions.
---

# Experiment with the agent's reasoning flow

Paths are relative to `core/`. The driver `.claude/skills/experiment-agent-flow/experiment.py`
imports `agent.graph.chat_graph.build_agent_graph` (the chat graph: `triage` → `pre_diagnosis`; the overrides below apply to the pre-diagnosis graph) and runs it in-process with an empty
`conversation_id` (so middleware emit nothing to Redis/SSE). It records every step
(model → tool calls → tool results → answer), auto-answers `ask_user`, and prints a comparison of
tool sequences across variants. For the full stack over HTTP/SSE use `/run-core` instead.

## Prerequisites

- Neo4j, Qdrant (with the KB loaded — see `/run-core` gotchas) and `.env` with the LLM key:
  `docker compose -f ../docker-compose.yml up -d` (Postgres/RabbitMQ/Redis/MinIO are NOT needed).
- `uv sync`. Run every command from `core/` with `uv run python` (first import loads the local
  embedding model, ~10 s).

## Run (agent path)

```bash
E=.claude/skills/experiment-agent-flow
# 1 question, default config: prints the trace, exits 0 if checks pass
uv run python $E/experiment.py "Bệnh chàm (eczema) là gì? Trả lời ngắn gọn." --model deepseek-v4-flash

# one-off variant: extra prompt text, tool subset, drop a middleware, repeat for variance
uv run python $E/experiment.py "Chào bạn" --model deepseek-v4-flash \
  --prompt-append "Luôn kết thúc câu trả lời bằng đúng chữ XONG." \
  --tools make_plan,ask_user --skip-middleware inject_long_term_memory --repeat 2 --parallel 2

# whole prompt replaced from a file (e.g. an edited copy of agent/prompt/orchestrator.py's text)
uv run python $E/experiment.py "Bệnh chàm là gì?" --model deepseek-v4-flash --system-prompt-file my_prompt.txt --quiet

# matrix: cases x variants (x --repeat), traces saved as JSON
uv run python $E/experiment.py --cases $E/examples/cases.json --variants $E/examples/variants.json \
  --parallel 3 --quiet --out /tmp/exp
```

- `--model` takes a short id from `AGENT_MODEL_CHOICES` (`deepseek-v4-flash`, ...) or a full
  `provider:model`. Omit it to use `settings.AGENT_MODEL`.
- Cases file: `[{"id", "question", "expect_tools"?, "forbid_tools"?, "answers"?}]`. `answers` are the
  replies fed to consecutive `ask_user` pauses (default: first option, else "Không rõ"; `--answer`
  sets them for a single question). Variants file: `{name: {model, system_prompt_file,
  prompt_append, tools, skip_middleware}}`. Middleware names: `select_model`,
  `inject_long_term_memory`, `emit_reasoning_step`, `emit_tool_result`.
- Output per run: numbered steps, `checks`, model calls, tool errors, tokens, the answer. With
  `--out` each run is `<case>__<variant>__<repeat>.json` (full steps, untruncated tool output).
- Built-in checks: `no_text_with_ask_user` (no prose in the same step as an `ask_user` call — that text is
  streamed to the FE then lost when the turn pauses), `plan_first` (first tool is `make_plan`, SYSTEM_PROMPT §3.0), `budget` (≤ 8 tool
  calls, §3), plus the case's `expect_tools`/`forbid_tools`. Exit code 1 if any run errors or fails.
- `examples/ask_policy.json` checks the ask-now (`ask_user`) vs answer-and-ask-later policy in
  SYSTEM_PROMPT §6; run it with `--repeat 3` since single runs are noisy.
- `examples/expand_cases.json` + `examples/expand_variants.json` were written for the removed `expand_entity_context` tool (now `hybrid_retrieval`'s KG leg / `knowledge_graph_search`) — rewrite them
  before reuse. In general the "without" variant still names the tool in the system prompt, so the model may call it and get an
  invalid-tool error — read `tool_errors` before trusting an A/B.
- Typical loop: change `agent/prompt/orchestrator.py` or a tool docstring (or pass the change as a
  variant), rerun the matrix, compare the "SO SÁNH CHUỖI TOOL" table and the JSON traces.

## Gotchas

- `build_agent_graph` accepts `tools`, `system_prompt`, `middleware` overrides (used by this
  driver); production callers pass none. `default_middleware()` (pre-diagnosis graph) returns the production list. Small-talk prompts are answered by the `triage` node before any tool runs — set `AGENT_TRIAGE_ENABLED=false` to exercise the pre-diagnosis graph on every prompt.
- Run with a real LLM: results vary run to run, so judge a change with `--repeat 3`+, not one run.
- `--tools` removes tools from the graph but NOT from the system prompt. The model still tries the
  missing tools and gets `X is not a valid tool, try one of [...]` (counted in `tool_errors`, not a
  failed check). Use it to see how the prompt degrades, and pair it with `--prompt-append` or a
  prompt file when you want a clean ablation.
- Vague-symptom questions used 9–12 tool calls in the sample run, over the prompt's 8-call budget,
  so the `budget` check fails there — a real finding, not a driver bug.
- Conversation id is empty on purpose: `emit_reasoning_step`/`emit_tool_result` skip publishing and
  `AgentContext.reasoning_steps` stays empty. Use the driver's own trace instead.
- Long-term memory is an in-memory store created per process, so `inject_long_term_memory` has
  nothing to recall unless a tool (`save_memory`) wrote it earlier in the same run.
- `classify_skin_image` needs MinIO and an attached image key; it is not exercised here.
- `--parallel N` prints traces after all runs finish (not interleaved); rate limits from the LLM
  provider can make parallel runs slow or fail (shows as `error` in the summary).

## Troubleshooting

- `ModuleNotFoundError: No module named 'app.core'` → the driver's settings import is stale after
  a core refactor; fix is `from app.config.settings import settings` (not `app.core.config`).
  Verified fixed 2026-10-03, smoke-tested with `$E "Chào bạn" --model deepseek-v4-flash --quiet`
  (`1/1 run đạt`). If this recurs after another refactor, check `core/app/config/settings.py`
  still exists at that path and update the import.
- `KeyError: 'deepseek-v4-x'` from `resolve_model` → not in `AGENT_MODEL_CHOICES`; use a listed id
  or a full `provider:model`.
- `tool không tồn tại: [...]` → a name in `--tools` doesn't match `ALL_TOOLS`; the message lists valid names.
- Tool results starting `Lỗi khi gọi công cụ ... 401` on KB tools → `QDRANT_API_KEY` missing in `.env`
  (see `/run-core`).
