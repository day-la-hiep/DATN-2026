# Derma AI Backend (core/)

Base project: **FastAPI + SQLAlchemy (async) + Redis Pub/Sub + RabbitMQ + LangChain/LangGraph + Celery**.

> ⚠️ Celery mới ở mức **tech stack đã thêm dependency + định hướng kiến trúc** (mục
> "Agent worker — Celery (định hướng)" bên dưới) — chưa refactor `app/agent/worker.py`
> để chạy qua Celery. Worker hiện tại vẫn dùng vòng consume RabbitMQ thủ công (aio-pika).

## Cấu trúc

```
core/
├── main.py                    → FastAPI app, lifespan (connect/close infra)
├── app/
│   ├── core/
│   │   ├── config.py          → Settings đọc từ .env (pydantic-settings)
│   │   ├── constants.py       → tên queue (RabbitMQ), channel (Redis), key active-turn
│   │   └── ids.py             → sinh id (new_user_id/new_conversation_id/new_message_id)
│   ├── db/
│   │   ├── base.py            → SQLAlchemy DeclarativeBase + naming convention
│   │   └── session.py         → async engine, session factory, get_db() (auto commit/rollback)
│   ├── infra/
│   │   ├── redis_client.py    → redis client + publish/subscribe/psubscribe/get/set/delete
│   │   └── rabbitmq_client.py → RabbitMQClient (connect/publish/consume)
│   ├── models/                → SQLAlchemy ORM: User, Conversation, Message
│   ├── dto/                   → Pydantic DTO — hợp đồng request/response API (camelCase)
│   │   ├── common.py          → CamelModel, ApiResponse[T] / PageResponse[T]
│   │   ├── conversation.py    → ConversationOutput, CreateConversationInput
│   │   ├── message.py         → MessageOutput, SendMessageInput, MessageMetadataDto, ...
│   │   └── health.py          → DTO cho /health, /health/ready
│   ├── repositories/          → truy vấn DB (SQLAlchemy), nhận/trả model ORM
│   │   ├── conversation_repository.py
│   │   └── message_repository.py
│   ├── services/               → business logic, nhận/trả DTO
│   │   ├── conversation_service.py
│   │   └── message_service.py  → turn mới/Steer/answer, publish RabbitMQ, Redis active-turn
│   ├── agent/                 → LangGraph Turn/Step/Reasoning (xem bên dưới)
│   │   ├── state.py           → TurnState, StepResult, ReasoningResult
│   │   ├── llm.py             → chat model (LangChain init_chat_model, cache, bind_tools)
│   │   ├── tools.py           → tool `ask_user` (hỏi lại user)
│   │   ├── schemas.py         → TurnRequest — payload RabbitMQ Core ↔ Worker
│   │   ├── graph.py           → StateGraph: pre_step / reasoning / ask_user_wait / finalize
│   │   └── worker.py          → tiến trình riêng: RabbitMQ → graph → Redis + Postgres
│   └── api/
│       ├── deps.py            → provider DI (get_conversation_service, get_message_service)
│       ├── health.py          → GET /health, /health/ready
│       └── conversation_api.py → REST + SSE (conversations, messages, questions/answer, stream)
```

## Agent — model (LangChain) + Turn/Step/Reasoning (LangGraph)

Đặc tả đầy đủ: [`app/kien-truc-agent.md`](app/kien-truc-agent.md). Tóm tắt phần đã cài:

### Chat model (`app/agent/llm.py`)

- `get_llm()` — khởi tạo chat model qua `langchain.chat_models.init_chat_model`, cấu hình
  từ `.env` (`AGENT_MODEL` theo cú pháp `"provider:model"`; `AGENT_TEMPERATURE`). Kết quả được
  `@lru_cache` vì model dùng chung cho mọi node reasoning trong cả process.
- `get_llm_with_tools(tools)` — bind tool vào chat model (`bind_tools`); `graph.py` bind
  `[ask_user_tool]` (`app/agent/tools.py`) — chưa có tool nghiệp vụ nào khác.
- **Mặc định: Gemini 3.5 Flash-Lite** (`AGENT_MODEL=google_genai:gemini-3.5-flash-lite`) —
  package `langchain[google-genai]` đã có sẵn trong `pyproject.toml`, chỉ cần set
  `GOOGLE_API_KEY` trong `.env`. Đổi provider khác (vd OpenAI): sửa `AGENT_MODEL` +
  `uv add langchain-openai` + set `OPENAI_API_KEY`.

### Graph (`app/agent/graph.py`)

```
START → pre_step ──(continue)──→ reasoning ──┐ còn tool_call (không phải ask_user) → lặp lại reasoning
           ▲                                  │
           └──────────────────────────────────┘
           │                                  │ gọi tool ask_user
           └──(answer)──→ finalize → END       └──→ ask_user_wait ──interrupt()──→ (chờ resume) ──→ reasoning
```

- `pre_step`: đọc `MessageRepository.list_pending_steers` (Postgres) để append Steer đang chờ
  vào context; quyết định `outcome` (`continue`/`answer`) — không LLM (rule thuần).
- `reasoning`: **1 Reasoning = đúng 1 hành động** — HOẶC gọi LLM, HOẶC thực thi 1 tool mà lần
  gọi LLM ngay trước vừa yêu cầu (KHÔNG BAO GIỜ gộp 2 việc, xem `app/kien-truc-agent.md` mục 0
  — nhầm lẫn này từng có ở 1 bản draft trước). Tự nhận biết đang ở phase nào bằng cách nhìn
  message cuối cùng (`AIMessage` còn `tool_calls` chưa thực thi → phase "gọi tool"). Còn việc
  phải làm (vừa gọi LLM ra tool_call, hoặc vừa thực thi tool xong) → tự lặp lại chính nó (vẫn
  trong cùng Step). Gặp tool `ask_user` → sang `ask_user_wait`. Gọi LLM mà không yêu cầu tool
  nào nữa → Step đóng, quay về `pre_step`.
- `ask_user_wait`: `interrupt()` — tạm dừng graph (checkpointer `InMemorySaver`, dev-only —
  xem `app/kien-truc-agent.md` mục 3 cho lựa chọn production), chờ resume qua
  `POST .../questions/{questionId}/answer`.
- `finalize`: chốt câu trả lời cuối.

### Worker (`app/agent/worker.py`)

Tiến trình riêng (không chạy trong process FastAPI): consume `agent_request_queue` (RabbitMQ)
→ chạy graph (turn mới hoặc `Command(resume=...)`) → publish từng Reasoning lên Redis
`agent:events:{conversation_id}` (giả lập streaming bằng cách chunk `content`, chưa stream
token thật từ LLM) → **ghi thẳng Postgres** khi turn tạm dừng (`status="question"`) hoặc kết
thúc (`status="done"`) — đơn giản hoá so với đặc tả relay qua `agent_response_queue`
(`docs/async-api-doc.md` mục 6), vì worker và Core dùng chung 1 package `app`.

Chạy worker (cần `AGENT_MODEL` trỏ tới provider đã cài + API key trong `.env`):

```bash
cd core && python -m app.agent.worker
```

## Agent worker — Celery (định hướng)

Dự kiến chuyển `app/agent/worker.py` (vòng consume RabbitMQ thủ công) sang **Celery** để tổ
chức task tốt hơn: retry/backoff tự động, giới hạn concurrency (`--concurrency`), theo dõi qua
Flower, và dễ mở rộng thêm loại task khác ngoài "1 turn agent" (vd task ingest tài liệu, task
gửi email...) mà không phải tự viết thêm consumer.

- **Broker**: tái dùng `RABBITMQ_URL` đã có (không cần thêm infra).
- **Result backend**: tái dùng Redis đã có (`redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}`),
  hoặc `rpc://` nếu không cần lưu kết quả (vì kết quả turn đã publish qua Redis Pub/Sub +
  RabbitMQ `agent_response_queue` như hiện tại).
- **Cấu trúc dự kiến**:
  ```
  app/agent/
  ├── celery_app.py   → Celery app instance (broker/backend từ settings)
  └── tasks.py         → @celery_app.task run_agent_turn(conversation_id, content, corr_id)
                          — gọi lại logic run_turn() hiện có trong worker.py
  ```
- **Lệnh chạy dự kiến**:
  ```bash
  celery -A app.agent.celery_app worker --loglevel=info
  ```
- API `conversation_api` (khi được thêm) sẽ gọi `run_agent_turn.delay(...)` thay vì tự publish
  message vào RabbitMQ — Celery lo phần serialize + đẩy vào queue.

## Chạy dev

```bash
# 1) Infra (Postgres/Redis/RabbitMQ) — xem docker-compose.yml ở gốc repo
docker compose up -d

# 2) Cài dependency
uv sync

# 3) Copy env
cp .env.example .env

# 4) Chạy server
python main.py
# → http://localhost:3050/status
# → http://localhost:3050/api/v1/health/ready
# → http://localhost:3050/docs (Swagger UI) — thử conversation_api ở đây

# 5) (Tuỳ chọn) chạy Agent Worker để test hết luồng chat thật — mặc định dùng
#    Gemini 2.0 Flash-Lite (đã cài langchain[google-genai]), cần set GOOGLE_API_KEY
#    trong .env. Đổi provider khác: xem AGENT_MODEL trong app/core/config.py.
cd core && python -m app.agent.worker
```

## Quy ước coding

Xem [`quy-uoc.md`](docs/quy-uoc.md) — vai trò từng layer, quy ước DTO (Pydantic) vs Model
(SQLAlchemy), async, Dependency Injection (FastAPI `Depends`), cấu hình, type checking, và
hướng dẫn từng bước khi thêm model/DTO/endpoint/kênh Redis/queue RabbitMQ/node reasoning mới.

## Ghi chú

- DB dùng SQLAlchemy **async** (driver `asyncpg`). `Base.metadata.create_all` chạy tự động
  lúc startup cho tiện dev — khi lên production nên chuyển sang Alembic migration.
- Giá trị mặc định trong `.env.example` khớp với `docker-compose.yml` ở gốc repo, nên chạy
  `docker compose up -d` xong là dùng được ngay, không cần chỉnh gì thêm.

## Tài liệu liên quan

- [`docs/quy-uoc.md`](docs/quy-uoc.md) — quy ước coding chi tiết cho `core/`.
- [`docs/api-doc.md`](docs/api-doc.md) — đặc tả REST API (Conversation, Message); máy đọc
  được: [`docs/openapi.yaml`](docs/openapi.yaml) (sinh tự động, `python scripts/gen_openapi.py`).
- [`docs/async-api-doc.md`](docs/async-api-doc.md) — đặc tả SSE (event catalog, Steer, persist
  rule); máy đọc được: [`docs/asyncapi.yaml`](docs/asyncapi.yaml) (viết tay).
- [`docs/db-diagram.md`](docs/db-diagram.md) — schema DB (User/Conversation/Message) + quy ước `metadata` JSONB.
- [`../docs/kien-truc-he-thong.md`](../docs/kien-truc-he-thong.md) — kiến trúc toàn hệ thống (FE ↔ Core ↔ Agent Worker ↔ DB/Redis/RabbitMQ).
- [`app/kien-truc-agent.md`](app/kien-truc-agent.md) — mô hình turn/step/reasoning bên trong Agent.
- [`../fe/docs/backend-contract.md`](../fe/docs/backend-contract.md) — hợp đồng API (REST + SSE) với Frontend.
