---
name: run-core
description: Run, start, drive, smoke-test and typecheck the Derma core backend (FastAPI API on :3050 + LangGraph agent worker over RabbitMQ/Redis/SSE). Use when asked to run core, start the agent worker, send a chat message to the agent, test a tool/middleware change end-to-end, or run pyright.
---

# Run `core` (FastAPI + agent worker)

Paths are relative to `core/`. Two processes: the API (`main.py`, port 3050) and the agent
worker (`agent/worker.py`). A chat turn only runs when a client opens the SSE stream, so
the driver (`.claude/skills/run-core/driver.py`, stdlib only) does create → stream → print.

## Prerequisites

Infra containers from the repo-root compose (postgres, redis, rabbitmq, qdrant, neo4j, minio):

```bash
docker compose -f ../docker-compose.yml up -d
docker ps --format '{{.Names}} {{.Status}}'
```

`.env` must exist (copy `.env.example`; needs a real LLM key for `AGENT_MODEL`, e.g. the
DeepSeek/OpenRouter key). Deps: `uv sync`.

## Run (agent path)

```bash
# 1. API (skip if `curl -s localhost:3050/status` already answers — port 3050 in use means it's up)
uv run python main.py > /tmp/api.log 2>&1 &
# 2. worker — MUST be running or chat turns hang until timeout
uv run python -u -m agent.worker > /tmp/worker.log 2>&1 &
# 3. drive it (skill lives at repo root, not under core/ — hence ../)
D=../.claude/skills/run-core/driver.py
python3 $D health                                   # database/redis/rabbitmq ok
python3 $D models                                   # valid --model ids
python3 $D chat "Bệnh chàm là gì?" --model deepseek-v4-flash
```

`chat` prints `conversationId`, then each SSE event (`message.started`, `message.thinking`,
`message.tool_result`, `message.done`), then `ANSWER: ...` (deltas joined). Other commands:
`send <convId> "<msg>"`, `messages <convId>`, `answer <convId> <questionId> <optionId> "<label>"`.
Exit codes: 0 = `message.done`, 2 = error/timeout, 3 = agent paused with `message.question`
(copy `questionId` and an option `id` from that event into `answer` to resume — verified).

The driver reads `APP_ACCESS_TOKEN` from env or `./.env` and sends it as a Bearer header
(API returns 401 without it when the token is set).

## Typecheck

`pyright` runs in basic mode (`typeCheckingMode` in `pyproject.toml`):

```bash
pyright agent/tools agent/middleware agent/graph agent/prompt agent/turn.py agent/worker.py
```

## Run (human path)

`uv run python main.py` (uvicorn, `reload=True`) and `uv run python -u -m agent.worker` in two
terminals, then the Next.js app in `../fe` (`pnpm dev`). Not usable headless.

## Gotchas

- `python -m agent.worker` (package `agent`, not `app.agent`) — the old `app.agent.*` paths no
  longer exist after the refactor; any leftover `from app.agent...` import fails.
- `agent/graph/common.py` is a leaf module on purpose: `pre_diagnosis_graph` imports `middleware/*`,
  so middleware must never import `pre_diagnosis_graph` or `chat_graph` (circular `ImportError` at worker start).
- Worker and API both die at startup with `AMQPConnectionError ... 5672` if RabbitMQ isn't up;
  it's the infra, not the code.
- `send`/`chat` against an unknown conversation id returns HTTP 500 (not 404).
- Run exactly ONE worker. Two consumers share `agent_request_queue` round-robin, but the checkpointer
  and long-term store are in-memory per process, so turns of one conversation land on different
  processes and the agent "forgets" earlier messages (seen: same-conversation follow-up answered
  "you haven't told me"). Check with `docker exec derma-rabbitmq rabbitmqctl list_queues name consumers`
  (expect `agent_request_queue 1`). A worker restart/auto-reload also wipes all conversation memory.
- Qdrant in compose has `QDRANT__SERVICE__API_KEY=derma_qdrant_2026`; `.env` needs
  `QDRANT_API_KEY=derma_qdrant_2026` (read by `app/infra/qdrant_client.py`), else `hybrid_retrieval`
  returns a failed-leg note (`401 Must provide an API key`). The book-chunk collection
  `derma_document_chunks_v2` is empty on a fresh Qdrant — upload and index a book in `/admin/documents`
  (or the retrieval returns no `book` results). Restart the worker after changing `.env`.

## Troubleshooting

- `ImportError: cannot import name '_MAX_CRITIC_RETRIES' from partially initialized module
  'agent.graph.pre_diagnosis_graph'` → a middleware imported from `pre_diagnosis_graph`; import from
  `agent.graph.common` instead.
- `[Errno 98] Address already in use` from `main.py` → an API is already on :3050; reuse it.
- `chat` hangs then times out → worker not running; check `tail /tmp/worker.log` for
  `listening on 'agent_request_queue'`.
