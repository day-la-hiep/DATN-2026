---
name: derma-core-conventions
description: Conventions for the Derma `core/` backend and its LangGraph agent — how files are organized (`app/` vs `agent/`), the request→RabbitMQ→worker→Redis→SSE flow, and the step-by-step way to add an endpoint, DTO, model, agent tool, middleware or prompt change. Use whenever the user asks to add or modify a tool, middleware, endpoint, service, repository, DTO, model, the agent graph or system prompt, asks where code should live, why an import is circular, or how a chat turn flows through core — even if they don't say "convention".
---

# Derma `core/` — flow and file conventions

Paths are relative to `core/`. Two independent processes share code but never import each
other's runtime: **Core** (FastAPI, `main.py`, package `app/`) and the **Agent worker**
(`python -m agent.worker`, package `agent/`). To run/drive/typecheck them, use `/run-core`.
Detailed backend-layer rules live in `docs/quy-uoc.md` (read it for DI, DTO/ORM split, envelope
details); this skill covers the flow, where things go, and the agent side, which that doc predates.

## The flow of one chat turn

```
POST /conversations[/{id}/messages]   Core saves user msg + queued assistant msg, stores the
        │                             TurnRequest in Redis  agent:pending_turn:{conv}  (NOT sent yet)
GET  /conversations/{id}/stream       Core subscribes to Redis channel agent:events:{conv}, THEN
        │                             GETDELs the pending turn and publishes it → agent_request_queue
        ▼                             (deferring avoids losing early events: Pub/Sub has no replay)
agent worker  (agent/turn.py)  runs agent_graph.astream(); publishes message.started/thinking/
        │                             delta/tool_result/question/done to the Redis channel → SSE → FE
        ▼
agent_response_queue                  AgentResponseMessage → Core's consumer is the ONLY writer of the
                                      final assistant row (incl. reasoning steps in Message.extra)
```

`ask_user` uses LangGraph `interrupt()`: the worker emits `message.question`, the turn pauses;
`POST .../questions/{id}/answer` queues a `TurnRequest(type="resume")` and the graph continues via
`Command(resume=...)`. Queue/channel/key names are constants in `app/core/constants.py` — never
hardcode them. The Core↔Worker contract is `agent/dto/schemas.py` (`TurnRequest`,
`AgentResponseMessage`); change both sides together.

## Layout

| Path | Owns | Must not |
|---|---|---|
| `app/api/` | FastAPI routers, `deps.py` providers | hold SQL or business logic |
| `app/services/` | business logic, takes/returns DTOs | touch FastAPI |
| `app/repositories/` | SQLAlchemy queries; `flush()` only, `get_db` commits | commit/rollback |
| `app/models/` | ORM tables only — SQLAlchemy persistence schema (register in `app/models/__init__.py`) | leak into API responses, hold business/domain fields that belong in `dto/base` |
| `app/dto/base/` | **the business entity layer** — domain objects (`Document`, `Conversation`, `User`, ...), the source of truth for what fields a business concept has | import ORM models |
| `app/dto/common/` | cross-resource shared DTOs, package split by topic: `envelope.py` (`ApiResponse[T]`), `file.py` (`FileDto(File)` — inherits base), `consultation.py` (`DoctorDto`/`ConsultationSessionDto` — trimmed base entities, never expose `password_hash`). Wire is snake_case — no camelCase aliases. **Base is the single source of truth**: when a wire shape is identical to a base entity (`VideoCall`...) use the base class directly or subclass it (`FileDto(File)`), don't redeclare fields. Data that is only stored as JSON inside a row, never as its own table (`Step`, `MessageChoice`, `Source`, in `common/chat.py`), is not a base entity | hold resource-specific fields |
| `app/dto/request/` | per-resource **Input** DTOs (`XxxInput`) — what an endpoint accepts | hold Output/response shapes |
| `app/dto/response/` | per-resource **Output** DTOs (`XxxOutput`/`XxxResult`) — what an endpoint returns | hold Input/request shapes |
| `app/infra/` | per-service clients: redis, rabbitmq, qdrant, minio, llm, docling, embedding | resource-specific business logic |
| `app/config/` | `settings.py` (only place for env vars, `AGENT_MODEL_CHOICES`), `constants.py`, `ids.py`, `auth.py` (renamed from `app/core/` — older docs/skills may still say `app/core/config.py`, that path no longer exists) | |
| `app/exception/` | `exception_handler.py` registered in `main.py`, `errors.py` | |
| `agent/graph/chat_graph.py` | **chat graph** (outermost): `build_chat_graph()`, `agent_graph`, `config_for()` (thread_id = conversation_id); nodes `triage` → `pre_diagnosis` | be imported by middleware |
| `agent/graph/triage.py` | `triage` node: intent filter, answers small talk / out-of-scope directly | |
| `agent/graph/pre_diagnosis_graph.py` | **pre-diagnosis graph** (`create_agent`): `ALL_TOOLS`, `default_middleware()`, `build_pre_diagnosis_graph()` | be imported by middleware |
| `agent/graph/common.py` | **leaf module**: `emit`, `TOOL_DISPLAY_NAMES`, `CriticState`, constants | import graph/middleware |
| `agent/middleware/` | `@wrap_model_call` / `@wrap_tool_call` / `@after_model` hooks (pre-diagnosis graph only) | import `chat_graph` / `pre_diagnosis_graph` |
| `agent/tools/` | one `@tool` per file (or small family) | import FastAPI |
| `agent/context/` | `agent_context.py` = `AgentContext` dataclass (per-turn data tools read via `runtime.context`); `builder.py` = `build_context(req)` that fills it from the DB/request | run the graph |
| `agent/worker.py` | process entry only: consume queue, per-conversation lock, `main` | hold turn logic |
| `agent/turn.py` | one turn (agent logic): build `AgentContext`, stream graph, finish (done / `ask_user` question / error) | |
| `agent/publisher.py` | worker → backend only (no agent logic): `emit` + `finish_turn` (SSE event → `[DONE]` → `agent_response_queue`) | import graph/tools/middleware |
| `app/workers/agent_response_consumer.py` | Core-side consumer of `agent_response_queue` that persists the assistant row (runs in Core, not the agent worker) | import from `agent/` beyond `agent/dto/schemas.py` |
| `agent/prompt/` | `orchestrator.py` (SYSTEM_PROMPT of the pre-diagnosis graph), `triage.py` (short intent-filter prompt), `critic.py` | |
| `agent/dto/schemas.py` | RabbitMQ message contract | |

Dependency direction is one-way: `chat_graph → pre_diagnosis_graph → middleware/tools → common/state`.
That's why shared helpers sit in `common.py`: a middleware importing `pre_diagnosis_graph` (which imports the middleware to
assemble the agent) raised `ImportError ... partially initialized module`. If something is needed by
both sides, move it down into `common.py`, don't import upward.

## `dto/base` is the business entity layer — gate changes here

`app/dto/base/` holds the canonical business entities (patient, doctor, document, conversation,
message, ...) — it is the source of truth for what fields a domain concept has, independent of how
it's persisted (`app/models/`, SQLAlchemy schema) or how it's exposed over the API (`app/dto/<resource>.py`).
Models exist to store an entity; `dto/base` entities exist to define it.

Within `app/dto/`, the per-resource files split further into groups: `base/` (entities, above),
`common/` (shared cross-resource DTOs — envelope, `FileDto`), `request/` (Input DTOs,
one concern per endpoint body/query) and `response/` (Output DTOs). A resource like `conversation`
or `message` gets its Input shapes under `request/` and Output shapes under `response/` rather than
mixed in one flat file — existing flat files (`app/dto/conversation.py`, `app/dto/message.py`) predate
this split and should move into it as they're touched, not all at once.

**Any change to `app/dto/base/` (adding/removing/renaming a field, adding a new entity, changing a
relationship) must be proposed and approved by the user before touching dependent code** (models,
repositories, services, API DTOs, agent tools). Don't cascade edits speculatively — present the
`dto/base` change first, wait for confirmation, then implement the ripple effects.

## Recipes

**Add an endpoint** — DTOs in `app/dto/<resource>.py` (`XxxInput`/`XxxOutput`) → repository method →
service method → route in `app/api/` with `response_model=ApiResponse[...]` and a `Depends(get_xxx_service)`
provider in `deps.py`; include the router in `main.py` under `settings.API_V1_PREFIX` (protected
routers take `dependencies=[Depends(require_app_token)]`). Update `docs/openapi.yaml`/`api-doc.md`.

**Add a model** — file in `app/models/`, subclass `Base`, import it in `app/models/__init__.py`
(the aggregator — otherwise `Base.metadata` doesn't see it and Alembic autogenerate misses it).
Schema is Alembic-managed (`core/migrations/`, no `create_all` in `main.py`): after adding/changing
a model run `uv run alembic revision --autogenerate -m "..."`, read the generated file, then
`uv run alembic upgrade head` (see `/run-core`).

**Add an agent tool** — new file in `agent/tools/`, `@tool` with a Vietnamese docstring that tells
the LLM *when* to call it and what each arg means (the docstring is the prompt). Need turn data →
`runtime: ToolRuntime[AgentContext, Any]`. Then: append to `ALL_TOOLS` in `pre_diagnosis_graph.py`, add a
friendly label to `TOOL_DISPLAY_NAMES` in `common.py` (else FE shows the raw function name), and
mention it in `agent/prompt/orchestrator.py` if the model must be steered to use it.

**Add middleware** — function in `agent/middleware/`, register it in `default_middleware()` in
`pre_diagnosis_graph.py`; order matters (`select_model` first so later hooks see the chosen model).
Anything pushed to the user goes through `emit(conversation_id, payload)`; keep event shape stable —
the FE depends on `type/tool/content/conversationId/messageId`.

**Add per-turn state** — add a field to `AgentContext`, set it where the worker builds it
(`agent/context/builder.py::build_context`), read it in tools/middleware via `runtime.context`.

**Add a setting** — declare in `Settings` (`app/config/settings.py`), mirror it in `.env.example`; a
worker restart is needed to pick up `.env` changes. Model choices for the UI are
`AGENT_MODEL_CHOICES` (short id → `provider:model`).

## Code style

- All I/O is `async`; never call blocking code inside `async def`.
- Comments and docstrings are Vietnamese and explain *why*, not what; match the surrounding file.
- **No long module docstrings at the top of a file and no multi-line docstrings on functions/classes**
  (no design history, flow narration, or incident write-ups). Default to no docstring; if one is
  needed, a single line; for a non-obvious line, a short inline comment right at that line. Only
  exception: `@tool` docstrings in `agent/tools/` — they are the LLM's prompt (see "Add an agent tool").
- Pyright runs in **basic** mode (`pyproject.toml`): `pyright agent app main.py` is clean (0
  errors, verified 2026-10-03). Basic mode does not flag partially-unknown library types, so
  don't add `# pyright: ignore` or `cast` just to silence those; fix real errors instead. Some
  `# pyright: ignore[...]` left over from the strict era are harmless. Prefer public names for
  cross-module helpers (no leading underscore).
- Import the new package paths: `from agent...`, never the old `from app.agent...` (removed by the refactor).

## Known loose ends (verify before relying on them)

The live consumer is `app/workers/agent_response_consumer.py`, imported by `main.py`.
`README.md` (root + `core/`) and `core/docs/quy-uoc.md`/`async-api-doc.md` still mention the old
`app/agent/...` paths and `python -m app.agent.worker` — that layout no longer exists (it's
`agent/...` and `python -m agent.worker`); don't follow those docs for paths.
