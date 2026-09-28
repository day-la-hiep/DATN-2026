# Kiến trúc tổng quan hệ thống

Tài liệu này mô tả bức tranh toàn hệ thống Derma AI (chatbot tư vấn da liễu). Xem thêm:
- [`core/app/kien-truc-agent.md`](../core/app/kien-truc-agent.md) — mô hình turn/step/reasoning bên trong Agent.
- [`core/README.md`](../core/README.md) — cấu trúc code, quy ước, cách chạy Backend.
- [`core/docs/quy-uoc.md`](../core/docs/quy-uoc.md) — quy ước coding chi tiết cho `core/`.
- [`core/docs/api-doc.md`](../core/docs/api-doc.md) / [`async-api-doc.md`](../core/docs/async-api-doc.md) — đặc tả REST + SSE của Core.
- [`core/docs/db-diagram.md`](../core/docs/db-diagram.md) — schema DB (User/Conversation/Message).
- [`fe/docs/backend-contract.md`](../fe/docs/backend-contract.md) — hợp đồng API đầy đủ (REST + SSE) giữa FE và Backend.

## 1. Thành phần

```
┌─────────────┐  REST + SSE   ┌──────────────┐   RabbitMQ    ┌───────────────┐
│  Frontend   │──────────────▶│    Core      │──────────────▶│  Agent Worker │
│  (Next.js)  │◀──────────────│  (FastAPI)   │◀──────────────│ (LangGraph)   │
└─────────────┘   /api/v1/*   └──────┬───────┘ agent_request/ └───────┬───────┘
                                      │         agent_response         │
                                      │                                 │
                              ┌───────▼───────┐                 ┌───────▼───────┐
                              │  PostgreSQL   │                 │  Redis Pub/Sub │
                              │ (SQLAlchemy)  │                 │ agent:events:* │
                              └───────────────┘                 │ (mỗi reasoning │
                                                                  │  step + delta) │
                                                                  └───────┬───────┘
                                                                          │
                                              Core subscribe & forward ◀─┘
                                              nguyên văn qua SSE
                                              (/conversations/{id}/stream)
```

| Thành phần | Vai trò | Công nghệ | Vị trí |
|---|---|---|---|
| **Frontend** | Giao diện chat | Next.js 16, React 19, Zustand, TanStack Query | `fe/` |
| **Core (Backend)** | REST API + SSE gateway, persist DB, forward event realtime | FastAPI, SQLAlchemy (async), Redis, RabbitMQ | `core/` |
| **Agent Worker** | Chạy vòng lặp reasoning (turn/step), gọi LLM, thực thi tool | LangChain, LangGraph (dự kiến tổ chức qua Celery) | `core/app/agent/` |
| **PostgreSQL** | Lưu hội thoại, tin nhắn, user | — | container `postgres` |
| **Redis** | Pub/Sub — stream từng reasoning step + message delta (agent → Core → SSE client), xem mục 3 | — | container `redis` |
| **RabbitMQ** | Hàng đợi request/response giữa Core ↔ Agent Worker | — | container `rabbitmq` |

> Luồng hiện tại của dự án chỉ gồm **chat + reasoning** — không có tính năng soạn thảo văn
> bản (canvas/OnlyOffice). `fe/` vẫn còn code editor OnlyOffice từ trước (`components/onlyoffice/`,
> `fe/docs/backend-contract.md` mục 3.5) nhưng **ngoài phạm vi** kiến trúc mô tả ở đây.

Infra (Postgres/Redis/RabbitMQ) chạy qua `docker-compose.yml` ở gốc `derma_hospital/`.
Core, Agent Worker, Frontend hiện chạy thủ công trong dev (`python main.py`,
`python -m app.agent.worker`, `pnpm dev`) — chưa container hoá.

## 2. Vì sao tách Core và Agent Worker thành 2 tiến trình

- **Core** chỉ có trách nhiệm: nhận HTTP request, ghi DB, publish request vào RabbitMQ, và
  forward sự kiện realtime từ Redis ra SSE client — **không gọi LLM trực tiếp**.
- **Agent Worker** là tiến trình riêng biệt, tách khỏi vòng đời HTTP request: nhận turn từ
  RabbitMQ, chạy graph LangGraph (có thể mất vài giây tới vài chục giây), stream từng bước
  reasoning qua Redis Pub/Sub.
- Lợi ích: Core luôn phản hồi nhanh (không bị block bởi LLM), scale Agent Worker độc lập
  (nhiều worker cùng consume 1 queue), và dễ thay LLM/agent logic mà không đụng tới API layer.

## 3. Stream reasoning realtime: Agent Worker → Redis Pub/Sub → Core → SSE

Toàn bộ **các bước reasoning** trong lúc Agent Worker xử lý — không chỉ câu trả lời cuối cùng —
đều được stream realtime tới Frontend, theo đường:

```
Agent Worker                 Redis Pub/Sub                      Core                     Frontend
(mỗi reasoning step) ──publish──▶ agent:events:{conversation_id} ──subscribe──▶ (forward nguyên văn) ──SSE──▶ (nghe /conversations/{id}/stream)
```

- **Agent Worker** publish lên Redis **mỗi khi có 1 sự kiện mới trong lúc suy luận** — không
  đợi cả turn xong mới gửi 1 lần. Theo `kien-truc-agent.md`, mỗi *reasoning step* (nằm bên
  trong 1 *step* nội bộ) sinh ra 1 chuỗi sự kiện `reasoning.step_started` →
  `reasoning.step_delta` (lặp nhiều lần) → `reasoning.step_completed`; câu trả lời cuối cùng
  cũng stream tương tự qua `message.delta*` → `message.done` (xem
  `fe/docs/backend-contract.md` mục 3.3 cho danh sách event đầy đủ).
- **Core chỉ subscribe và forward y nguyên** — không transform, không buffer chờ đủ 1 turn.
  Đây là lý do Core được gọi là **pure forwarder**: route `GET /conversations/{id}/stream`
  chỉ làm 2 việc — `psubscribe`/`subscribe` kênh Redis đúng `conversation_id`, và với mỗi
  message nhận được, viết thẳng ra response dạng `data: <json>\n\n` cho SSE client.
- **Vì sao dùng Redis Pub/Sub cho việc này (không dùng RabbitMQ)**: RabbitMQ (`agent_request_queue`/
  `agent_response_queue`) theo mô hình *competing consumers* — 1 message chỉ 1 consumer nhận
  được, phù hợp cho việc phân phối 1 turn work-item. Redis Pub/Sub theo mô hình *broadcast* —
  mọi subscriber của kênh đều nhận được cùng lúc, phù hợp để forward sự kiện realtime tới
  đúng (các) Core instance đang giữ kết nối SSE của client đó (khi scale nhiều Core instance,
  mỗi instance tự subscribe kênh theo `conversation_id` mà nó đang phục vụ).
- **Không cần lưu lại các sự kiện Pub/Sub** — nếu SSE client mất kết nối giữa chừng, các
  reasoning step đã publish sẽ mất (Pub/Sub không replay). Câu trả lời cuối cùng (`message.done`)
  vẫn được đảm bảo lưu vào Postgres qua đường riêng RabbitMQ `agent_response_queue` (mục 4,
  bước 4) — tách khỏi luồng SSE nên không phụ thuộc client có đang nghe hay không.

## 4. Luồng 1 turn chat (end-to-end)

1. **FE** `POST /api/v1/conversations/{id}/messages` — Core lưu user message vào Postgres,
   publish `AgentTurnRequest` vào RabbitMQ (`agent_request_queue`), trả về ngay (không đợi
   agent xử lý xong).
2. **FE** mở `GET /api/v1/conversations/{id}/stream` (SSE) — Core subscribe Redis
   `agent:events:{conversation_id}` và forward mọi message nhận được ra client dưới dạng
   `data: {...}\n\n` (Core là **pure forwarder**, không transform).
3. **Agent Worker** consume `agent_request_queue`, chạy LangGraph (xem `kien-truc-agent.md`
   cho chi tiết turn/step/reasoning), publish từng **reasoning step** lên Redis
   `agent:events:{conversation_id}` theo thời gian thực (chi tiết ở mục 3).
4. Khi turn xong, **Agent Worker** publish kết quả hoàn chỉnh vào RabbitMQ
   (`agent_response_queue`); **Core** consume queue này để persist assistant message vào
   Postgres (tách khỏi luồng SSE — đảm bảo dữ liệu được lưu kể cả khi client đã đóng kết nối SSE).

## 5. Trạng thái hiện tại vs định hướng

| Hạng mục | Hiện tại | Định hướng |
|---|---|---|
| Core API layer (`app/api/`) | ✅ `conversation_api.py` theo `core/docs/api-doc.md` + `async-api-doc.md` (`/health` vẫn còn) | Thêm domain khác khi cần (không phải chat) |
| DB models (`app/models/`) | ✅ `User`, `Conversation`, `Message` theo `core/docs/db-diagram.md` | Alembic migration thay `create_all` khi lên production |
| DTO (`app/dto/`) | ✅ `common.py`, `health.py`, `conversation.py`, `message.py` | — |
| Agent reasoning loop | ✅ `pre_step` / `reasoning` (tự lặp) / `tool_wait` (interrupt, tổng quát cho mọi tool `requires_wait=True`) / `finalize` — đúng theo `kien-truc-agent.md` | Tool nghiệp vụ thật (ngoài `ask_user`), `sources` |
| Tổ chức Agent Worker | Vòng consume RabbitMQ thủ công (`app/agent/worker.py`, aio-pika); persist DB relay qua `agent_response_queue` (Core consume, `app/agent/response_consumer.py`) — đúng theo `async-api-doc.md` | Chuyển qua Celery task (`celery_app.py` + `tasks.py`) — xem `core/README.md` |
| Long-term memory | ✅ `app/agent/memory.py` — distill (LLM) mỗi turn xong → vector Qdrant; đầu turn mới semantic search theo `user_id` (trong + xuyên hội thoại) — xem `core/app/kien-truc-memory.md` | Ngưỡng liên quan/số lượng memory lấy về, dọn memory cũ |
| Container hoá | Infra (Postgres/Redis/RabbitMQ/Qdrant) qua `docker-compose.yml` | Core/FE vẫn chạy dev thủ công, chưa có Dockerfile |

## 6. Biến môi trường liên service

| Biến | Dùng bởi | Ghi chú |
|---|---|---|
| `DATABASE_URL` | Core | mặc định khớp `docker-compose.yml` |
| `REDIS_HOST` / `REDIS_PORT` | Core, Agent Worker | kênh `agent:events:{conversation_id}` |
| `RABBITMQ_URL` | Core, Agent Worker | queue `agent_request_queue` / `agent_response_queue` |
| `AGENT_MODEL` / `AGENT_TEMPERATURE` | Agent Worker | cú pháp `"provider:model"`, xem `core/README.md` |
| `QDRANT_URL` / `QDRANT_COLLECTION` | Agent Worker | long-term memory (vector), xem `core/app/kien-truc-memory.md` |
| `NEXT_PUBLIC_API_URL` / `BACKEND_URL` | Frontend | trỏ tới Core (`/api/v1`) |
| `NEXT_PUBLIC_USE_MOCK` | Frontend | `true` = chưa cần Core/Agent chạy, dùng mock trong `fe/services/mock/` |
