# Derma Hospital — AI Chat tư vấn da liễu

Ứng dụng chat tư vấn da liễu dùng AI Agent (LangGraph): người dùng trò chuyện với trợ lý AI,
trợ lý suy luận nhiều bước (có thể hỏi lại khi thiếu thông tin), stream câu trả lời theo thời
gian thực, và nhớ được thông tin người dùng qua các lần tư vấn khác nhau (long-term memory).

## 1. Kiến trúc tổng quan

```
┌─────────┐   REST + SSE    ┌──────────┐  RabbitMQ   ┌───────────────┐
│   FE    │ ───────────────▶│   Core   │────────────▶│  Agent Worker │
│(Next.js)│◀─────────────── │(FastAPI) │◀────────────│  (LangGraph)  │
└─────────┘   Redis Pub/Sub └────┬─────┘  RabbitMQ    └──────┬────────┘
                                  │                            │
                            ┌─────┴─────┐              ┌───────┴───────┐
                            │ PostgreSQL │              │ Redis │Qdrant │
                            └───────────┘              └───────────────┘
```

- **`fe/`** — Next.js (App Router), gọi REST + SSE của Core, quản lý state chat bằng Zustand.
- **`core/`** — FastAPI: REST API (conversations/messages/questions) + SSE (`/stream`, forward
  nguyên văn từ Redis Pub/Sub). Không tự chạy LLM — chỉ publish "turn request" vào RabbitMQ.
- **Agent Worker** (cũng nằm trong `core/`, chạy như 1 tiến trình riêng —
  `python -m app.agent.worker`) — consume RabbitMQ, chạy LangGraph (state machine
  Turn/Step/Reasoning), gọi LLM (Gemini), publish từng bước suy luận lên Redis theo thời gian
  thực, publish kết quả cuối vào RabbitMQ để Core ghi Postgres.
- **PostgreSQL** — lưu `users`/`conversations`/`messages` (nguồn sự thật duy nhất, chỉ Core ghi).
- **Redis** — Pub/Sub cho SSE realtime + 1 key đánh dấu "turn đang chạy" theo hội thoại.
- **RabbitMQ** — 2 hàng đợi: `agent_request_queue` (Core → Worker), `agent_response_queue`
  (Worker → Core, để Core tự ghi DB — Worker không đụng Postgres trừ vài chỗ ĐỌC).
- **Qdrant** — vector DB cho long-term memory (xem mục 3).

Tài liệu kiến trúc chi tiết:
- [`docs/kien-truc-he-thong.md`](docs/kien-truc-he-thong.md) — bức tranh toàn hệ thống.
- [`core/app/kien-truc-agent.md`](core/app/kien-truc-agent.md) — vòng lặp Turn/Step/Reasoning
  bên trong Agent (pre_step/reasoning/tool_wait/finalize), cơ chế `interrupt()`/resume.
- [`core/app/kien-truc-memory.md`](core/app/kien-truc-memory.md) — long-term memory.
- [`core/docs/api-doc.md`](core/docs/api-doc.md) / [`async-api-doc.md`](core/docs/async-api-doc.md)
  — đặc tả REST + SSE đầy đủ (event catalog, Steer, ask_user...).

## 2. Tính năng chính

- **Chat streaming thời gian thực**: token LLM được stream thật (không phải giả lập cắt chunk)
  ngay khi model sinh ra, qua SSE.
- **Agent tự hỏi lại khi thiếu thông tin** (tool `ask_user`): turn tạm dừng (`interrupt()`),
  chờ người dùng chọn/trả lời qua endpoint riêng, rồi resume đúng chỗ đã dừng — không mất
  ngữ cảnh, không tạo turn mới.
- **Steer**: gửi thêm tin nhắn "chen ngang" trong lúc agent đang xử lý — được nạp vào ngay khi
  agent kết thúc 1 bước suy luận, không cần chờ agent trả lời xong tin nhắn trước.
- **Long-term memory**: sau mỗi lượt trả lời, agent tự tóm tắt (bằng LLM) các thông tin đáng
  nhớ (tình trạng da, tiền sử, thuốc đã dùng/khuyến nghị, dị ứng...), lưu vector vào Qdrant.
  Ở lượt hỏi mới (dù cùng hội thoại hay hội thoại khác của cùng user), agent tự tìm lại các
  memory liên quan (semantic search) để trả lời nhất quán, không cần người dùng nhắc lại.

## 3. Cấu trúc thư mục

```
derma_hospital/
├── core/                 → Backend: FastAPI (Core) + Agent Worker (LangGraph)
│   ├── main.py           → entrypoint Core (REST + SSE)
│   ├── app/agent/        → LangGraph, LLM, tools, worker.py, memory.py
│   ├── app/api/          → REST endpoints
│   ├── app/models/       → SQLAlchemy ORM
│   ├── docs/             → đặc tả API (REST/SSE), DB diagram
│   └── README.md         → chi tiết backend (có thể đã hơi lệch, ưu tiên tài liệu ở trên)
├── fe/                   → Frontend Next.js
│   └── features/chat/    → store (Zustand), types, components
├── docs/                 → tài liệu kiến trúc toàn hệ thống
└── docker-compose.yml    → infra: Postgres, Redis, RabbitMQ, Qdrant
```

## 4. Yêu cầu môi trường

- Docker + Docker Compose (v2, lệnh `docker compose`).
- Python 3.12+ và [`uv`](https://docs.astral.sh/uv/) (quản lý dependency `core/`).
- Node.js 20+ và `pnpm` (quản lý dependency `fe/`).
- API key Google AI Studio (Gemini) — cho `AGENT_MODEL` (chat) và embedding (long-term memory).

## 5. Hướng dẫn chạy (dev)

### 5.1. Infra

```bash
docker compose up -d
docker compose ps   # xác nhận cả 4 container (postgres/redis/rabbitmq/qdrant) đều healthy/up
```

### 5.2. Backend (Core)

```bash
cd core
cp .env.example .env
# Mở .env, điền GOOGLE_API_KEY (bắt buộc — dùng cho cả chat model lẫn embedding memory)
uv sync
python main.py
```
- `python main.py` tự tạo bảng (`create_all`) lúc khởi động — không cần chạy migration tay.
- Kiểm tra: http://localhost:3050/status, Swagger UI tại http://localhost:3050/docs.

**Seed 1 user demo** (app chưa có auth thật — FE hard-code `userId: "user-1"`):
```bash
docker exec $(docker compose ps -q postgres) \
  psql -U postgres -d derma_hospital_db -c \
  "INSERT INTO users (id, name, email, created_at) VALUES ('user-1', 'Demo User', 'demo@local', now()) ON CONFLICT (id) DO NOTHING;"
```
(Chạy lệnh này SAU khi `python main.py` đã chạy ít nhất 1 lần — cần bảng `users` tồn tại trước.)

### 5.3. Agent Worker

Tiến trình riêng, bắt buộc phải chạy để agent thực sự trả lời (Core chỉ nhận request rồi đẩy
vào queue, không tự chạy LLM):

```bash
cd core
python -u -m app.agent.worker
```
`-u` (unbuffered) để thấy log ngay lập tức — mặc định Python buffer `print()` khi output không
phải terminal tương tác.

### 5.4. Frontend

```bash
cd fe
cp .env.local.example .env.local
# Trong .env.local: đặt NEXT_PUBLIC_USE_MOCK=false để dùng backend thật (mặc định true = mock)
pnpm install
pnpm dev
```
Mở http://localhost:3000.

## 6. Biến môi trường chính

### `core/.env`

| Biến | Ý nghĩa | Mặc định khớp `docker-compose.yml`? |
|---|---|---|
| `DATABASE_URL` | Kết nối Postgres (asyncpg) | ✅ |
| `REDIS_HOST` / `REDIS_PORT` | Redis Pub/Sub | ✅ |
| `RABBITMQ_URL` | RabbitMQ | ✅ |
| `QDRANT_URL` / `QDRANT_COLLECTION` | Long-term memory | ✅ |
| `AGENT_MODEL` | Chat model, cú pháp `"provider:model"` (vd `google_genai:gemini-3.5-flash-lite`) | — |
| `GOOGLE_API_KEY` | API key Gemini — **bắt buộc** phải tự điền | — |
| `AGENT_MAX_REASONING_STEPS` | Giới hạn an toàn số bước suy luận/turn | ✅ |

### `fe/.env.local`

| Biến | Ý nghĩa |
|---|---|
| `NEXT_PUBLIC_USE_MOCK` | `true` = chạy UI với data giả lập (không cần backend); `false` = gọi Core thật |
| `NEXT_PUBLIC_API_URL` | URL REST của Core (mặc định `http://localhost:3050/api/v1`) |
| `NEXT_PUBLIC_ONLYOFFICE_*` / `ONLYOFFICE_JWT_SECRET` | Chỉ cần cho tính năng soạn văn bản (canvas) — **chưa cần** cho luồng chat cơ bản |

## 7. Lưu ý / vấn đề hay gặp

- **Model Gemini có thể bị Google ngừng hỗ trợ theo thời gian** (đã gặp `gemini-2.5-flash-lite`
  → 404 NOT_FOUND, phải đổi sang `gemini-3.5-flash-lite`). Nếu gặp lỗi 404 tương tự, kiểm tra
  model còn dùng được không: `curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY"`.
- **DB không tự tạo nếu tái dùng volume Postgres cũ**: `POSTGRES_DB` trong `docker-compose.yml`
  chỉ có hiệu lực lúc container Postgres khởi tạo volume LẦN ĐẦU. Nếu volume đã tồn tại từ
  trước (vd đổi tên DB, hoặc dùng chung máy với project khác), cần tạo tay:
  `docker exec <container_postgres> psql -U postgres -c "CREATE DATABASE derma_hospital_db;"`.
- **Xung đột port với project Docker khác**: nếu máy có sẵn container Postgres/Redis/RabbitMQ
  khác chiếm cùng port (5432/6379/5672), container của repo này có thể "Up" nhưng KHÔNG publish
  được port ra host. Kiểm tra `docker port <container>` — nếu rỗng, `docker compose up -d
  --force-recreate` sau khi giải phóng port.
- **Core dùng `--reload`**: tự restart khi sửa code. Nếu có 1 kết nối SSE (`curl -N .../stream`)
  đang mở, reload sẽ treo ở "Waiting for connections to close" — đóng kết nối đó (Ctrl+C) để
  reload tiếp tục.
- **`GET /conversations` yêu cầu query `userId`** (chưa có auth thật) — FE tự gửi kèm, nhưng
  gọi trực tiếp qua `curl`/Swagger cần thêm `?userId=user-1`.
- Core từng tự mở 1 turn ma (content rỗng) mỗi khi tạo conversation mới, khiến LLM từ chối
  request và treo Redis "active_turn" key — **đã được vá**
  (`ConversationService.create_conversation` chỉ mở turn khi `initMessage` không rỗng); nếu
  thấy hành vi lạ ở bản cũ hơn, đây là nguyên nhân.

## 8. Tài liệu khác

- [`core/README.md`](core/README.md) — chi tiết cấu trúc code backend (1 số phần có thể hơi
  lệch so với các thay đổi gần đây — ưu tiên `docs/kien-truc-he-thong.md` và
  `core/app/kien-truc-agent.md`/`kien-truc-memory.md` nếu thấy mâu thuẫn).
- [`core/docs/quy-uoc.md`](core/docs/quy-uoc.md) — quy ước coding backend.
- [`core/docs/db-diagram.md`](core/docs/db-diagram.md) — schema DB.
