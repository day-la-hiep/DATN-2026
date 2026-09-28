# Derma Hospital — AI Chat tư vấn da liễu

Ứng dụng chat tư vấn da liễu dùng AI Agent (LangGraph): người dùng trò chuyện (kèm ảnh da) với
trợ lý AI, trợ lý suy luận nhiều bước, tra cứu guideline y khoa và knowledge graph, hỏi lại khi
thiếu thông tin, stream câu trả lời theo thời gian thực và nhớ thông tin người dùng qua các lần
tư vấn (long-term memory).

> Kết quả của AI **không phải chẩn đoán y khoa**. Dữ liệu guideline đang ở trạng thái chờ bác sĩ
> duyệt (`needs_clinical_review` / `needs_manual_verification`).

- **Deploy production (Docker Compose, kèm nạp dữ liệu): [`DEPLOY.md`](DEPLOY.md).**
- **Dữ liệu (guideline, knowledge graph) và cách nạp: [`core/data-ingest/README.md`](core/data-ingest/README.md).**

## 1. Kiến trúc tổng quan

```
┌─────────┐   REST + SSE    ┌──────────┐  RabbitMQ   ┌───────────────┐
│   FE    │ ───────────────▶│   Core   │────────────▶│  Agent Worker │
│(Next.js)│◀─────────────── │(FastAPI) │◀────────────│  (LangGraph)  │
└─────────┘   Redis Pub/Sub └────┬─────┘  RabbitMQ    └───────┬───────┘
                                 │                            │
                    ┌────────────┴───┐          ┌─────────────┼──────────────┬────────┐
                    │   PostgreSQL   │          │ Redis  Qdrant│  Neo4j       │ MinIO  │
                    │ (nguồn sự thật)│          │ pubsub memory│ PrimeKG+DermO│ ảnh    │
                    └────────────────┘          │ + guideline  │              │        │
                                                └──────────────┴──────────────┴────────┘
```

- **`fe/`** — Next.js (App Router), gọi REST + SSE của Core, state chat bằng Zustand.
- **`core/`** — FastAPI: REST (conversations/messages/questions/uploads) + SSE (`/stream`, forward
  nguyên văn từ Redis Pub/Sub). Không tự chạy LLM — chỉ publish "turn request" vào RabbitMQ.
- **Agent Worker** (nằm trong `core/`, tiến trình riêng: `python -m app.agent.worker`) — consume
  RabbitMQ, chạy LangGraph (state machine Turn/Step/Reasoning), gọi LLM qua **OpenRouter**, publish
  từng bước suy luận lên Redis theo thời gian thực, publish kết quả cuối vào RabbitMQ để Core ghi Postgres.
- **PostgreSQL** — `users`/`conversations`/`messages` (chỉ Core ghi).
- **Redis** — Pub/Sub cho SSE realtime + key đánh dấu "turn đang chạy" theo hội thoại.
- **RabbitMQ** — `agent_request_queue` (Core → Worker), `agent_response_queue` (Worker → Core).
- **Qdrant** — 2 collection: long-term memory (`agent_memories`) và guideline da liễu
  (`derma_kb_chunks`, 435 chunk từ 87 bệnh). Embedding chạy **local** (sentence-transformers).
- **Neo4j** — knowledge graph: PrimeKG lọc theo da liễu (`:Entity`) và ontology DermO (`:DermoTerm`).
- **MinIO** — lưu ảnh đính kèm tin nhắn; agent nhận ảnh qua object key.

Tài liệu kiến trúc chi tiết:
- [`docs/kien-truc-he-thong.md`](docs/kien-truc-he-thong.md) — toàn hệ thống.
- [`core/app/kien-truc-agent.md`](core/app/kien-truc-agent.md) — vòng lặp Turn/Step/Reasoning, `interrupt()`/resume.
- [`core/app/kien-truc-memory.md`](core/app/kien-truc-memory.md) — long-term memory.
- [`core/docs/api-doc.md`](core/docs/api-doc.md) / [`async-api-doc.md`](core/docs/async-api-doc.md) — REST + SSE (event catalog, Steer, ask_user…).

## 2. Tính năng chính

- **Chat streaming thời gian thực**: token LLM được stream thật qua SSE.
- **Agent dùng công cụ** (`core/app/agent/tools/`):

  | Tool | Việc | Nguồn |
  |---|---|---|
  | `search_disease_guidelines`, `get_disease_guideline_profile` | tra guideline BYT 75/2015, WHO, MedlinePlus | Qdrant |
  | `query_dermatology_kg` | hỏi đáp quan hệ bệnh–triệu chứng–thuốc–gen (sinh Cypher) | Neo4j (PrimeKG) |
  | `lookup_dermo_term` | chuẩn hoá thuật ngữ da liễu | Neo4j (DermO) |
  | `ground_medical_entities` | neo thực thể y khoa vào cả hai nguồn trên | Neo4j |
  | `classify_skin_image` | phân loại ảnh da (CNN 22 lớp) — chỉ là **giả thuyết**, không phải chẩn đoán | MinIO + PyTorch |
  | `ask_user`, `save_memory` | hỏi lại người dùng; lưu memory | — |
- **Agent tự hỏi lại khi thiếu thông tin** (`ask_user`): turn tạm dừng (`interrupt()`), chờ người
  dùng trả lời rồi resume đúng chỗ, không mất ngữ cảnh.
- **Steer**: gửi thêm tin nhắn "chen ngang" khi agent đang xử lý — nạp vào ngay sau bước suy luận hiện tại.
- **Đính kèm ảnh**: FE `POST /uploads` → MinIO → agent phân tích.
- **Long-term memory**: sau mỗi lượt, agent tóm tắt thông tin đáng nhớ (tình trạng da, tiền sử, thuốc,
  dị ứng…) vào Qdrant và tự tìm lại ở lượt sau, kể cả ở hội thoại khác của cùng user.

## 3. Cấu trúc thư mục

```
.
├── core/                     Backend: FastAPI (Core) + Agent Worker (LangGraph)
│   ├── main.py               entrypoint Core (REST + SSE)
│   ├── app/agent/            LangGraph, LLM, tools/, worker.py, memory.py, embeddings.py
│   ├── app/api/              REST endpoints (conversation, upload, health)
│   ├── app/{models,repositories,services,dto,infra,db}/
│   ├── data-ingest/          Xử lý dữ liệu theo nguồn (input → output) + nạp Qdrant/Neo4j
│   ├── docs/                 đặc tả API (REST/SSE), DB diagram, quy ước
│   └── Dockerfile            image dùng chung cho core-api và agent-worker
├── fe/                       Frontend Next.js (features/chat: store, types, components)
├── docs/                     tài liệu kiến trúc toàn hệ thống
├── notebook/                 thử nghiệm; model/model_output/ chứa checkpoint CNN
├── docker-compose.yml        infra DEV: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
├── docker-compose.prod.yml   stack PROD: infra + core-api + agent-worker + FE
├── reset-and-gen-data.sh     (prod) xoá và nạp lại dữ liệu Qdrant/Neo4j trong container
└── DEPLOY.md                 hướng dẫn deploy
```

## 4. Yêu cầu môi trường

- Docker + Docker Compose v2 (`docker compose`).
- Python 3.12+ và [`uv`](https://docs.astral.sh/uv/) (dependency của `core/`).
- Node.js 20+ và `pnpm` (dependency của `fe/`).
- API key [OpenRouter](https://openrouter.ai/keys) cho `AGENT_MODEL` (chat).

## 5. Chạy dev

### 5.1. Infra

```bash
docker compose up -d
docker compose ps    # 6 container: postgres, redis, rabbitmq, qdrant, neo4j, minio
```

Mọi giá trị trong `docker-compose.yml` ghi thẳng (không đọc `.env`) và khớp default của
`core/app/core/config.py`: Postgres `postgres:postgres@localhost:5432/derma_hospital_db`, Neo4j
`neo4j/derma12345`, MinIO `minio/minio123`, RabbitMQ `guest/guest`. Muốn đổi thì sửa thẳng file này.

### 5.2. Backend (Core)

```bash
cd core
cp .env.example .env      # điền OPENROUTER_API_KEY và APP_ACCESS_TOKEN
uv sync
python main.py
```
- Tự tạo bảng (`create_all`) lúc khởi động — không cần migration tay.
- Kiểm tra: http://localhost:3050/health, Swagger UI: http://localhost:3050/docs.

**Seed 1 user demo** (chưa có auth thật — FE hard-code `userId: "user-1"`), chạy SAU khi
`python main.py` đã chạy ít nhất 1 lần (cần bảng `users`):
```bash
docker exec derma-postgres psql -U postgres -d derma_hospital_db -c \
  "INSERT INTO users (id, name, email, created_at) VALUES ('user-1', 'Demo User', 'demo@local', now()) ON CONFLICT (id) DO NOTHING;"
```

### 5.3. Nạp dữ liệu (guideline + knowledge graph)

Qdrant và Neo4j mới tạo đều **trống** — agent sẽ không tra cứu được gì cho đến khi nạp. Dữ liệu sạch
đã có sẵn trong `core/data-ingest/01_normalize/output/`; chạy từ `core/`:

```bash
python data-ingest/01_normalize/scripts/load_knowledge_base.py   # chunk + embed → Qdrant
python data-ingest/01_normalize/scripts/load_primekg.py          # → Neo4j (PrimeKG)
python data-ingest/01_normalize/scripts/load_dermo.py            # → Neo4j (DermO)
```
Thêm `--reset` để xoá dữ liệu cũ trước khi nạp. Tạo lại dữ liệu từ nguồn thô (`python data-ingest/run.py …`):
xem [`core/data-ingest/README.md`](core/data-ingest/README.md).

### 5.4. Agent Worker

Tiến trình riêng, **bắt buộc** để agent trả lời (Core chỉ đẩy request vào queue):
```bash
cd core
python -u -m app.agent.worker
```
`-u` để thấy log ngay (Python buffer `print()` khi output không phải terminal).

Tool `classify_skin_image` cần checkpoint CNN tại `SKIN_CNN_CHECKPOINT_PATH` (mặc định
`<repo>/model/model_output/AdaptiveCNN_SkinDisease_v5_best.pth`; file hiện nằm ở
`notebook/model/model_output/` — đặt lại đường dẫn trong `core/.env` hoặc chép file về đúng chỗ).

### 5.5. Frontend

```bash
cd fe
cp .env.local.example .env.local
# NEXT_PUBLIC_USE_MOCK=false để dùng backend thật (mặc định true = data giả lập)
pnpm install
pnpm dev
```
Mở http://localhost:3000.

## 6. Biến môi trường chính

### `core/.env` (mẫu: `core/.env.example`)

| Biến | Ý nghĩa | Ghi chú |
|---|---|---|
| `DATABASE_URL`, `REDIS_*`, `RABBITMQ_URL`, `QDRANT_URL`, `NEO4J_*`, `MINIO_*` | kết nối hạ tầng | mặc định khớp `docker-compose.yml` |
| `QDRANT_COLLECTION` / `QDRANT_KB_COLLECTION` | memory / guideline | `agent_memories` / `derma_kb_chunks` |
| `AGENT_MODEL` | chat model, cú pháp `"provider:model"` | mặc định `openai:google/gemma-4-26b-a4b-it` (qua OpenRouter) |
| `OPENROUTER_API_KEY` | key OpenRouter | **bắt buộc**, tự điền |
| `APP_ACCESS_TOKEN` | token truy cập app | **bắt buộc**, tự điền |
| `AGENT_TEMPERATURE`, `AGENT_THINKING_LEVEL` | tham số LLM | |
| `SKIN_CNN_CHECKPOINT_PATH` | checkpoint CNN cho `classify_skin_image` | xem 5.4 |

### `fe/.env.local`

| Biến | Ý nghĩa |
|---|---|
| `NEXT_PUBLIC_USE_MOCK` | `true` = UI với data giả lập (không cần backend); `false` = gọi Core thật |
| `NEXT_PUBLIC_API_URL` | URL REST của Core (mặc định `http://localhost:3050/api/v1`) |
| `NEXT_PUBLIC_ONLYOFFICE_*`, `ONLYOFFICE_JWT_SECRET` | chỉ cho tính năng soạn văn bản (canvas) — không cần cho luồng chat |

## 7. Lưu ý / vấn đề hay gặp

- **Container "Up" nhưng backend `Connection refused`**: nếu máy có container Postgres/Redis/RabbitMQ… khác
  chiếm cùng cổng, container của repo có thể chạy mà KHÔNG publish được cổng ra host. Kiểm tra
  `docker port derma-postgres` — nếu rỗng, giải phóng cổng rồi `docker compose up -d --force-recreate`
  (dữ liệu trong volume không mất).
- **DB không tự tạo khi tái dùng volume Postgres cũ**: `POSTGRES_DB` chỉ có hiệu lực lúc khởi tạo volume
  LẦN ĐẦU. Nếu volume đã tồn tại, tạo tay:
  `docker exec derma-postgres psql -U postgres -c "CREATE DATABASE derma_hospital_db;"`.
- **Agent trả lời nhưng không tra được guideline/KG**: chưa nạp dữ liệu (mục 5.3), hoặc Neo4j/Qdrant chưa sẵn sàng.
- **Sau khi đổi dữ liệu PrimeKG** phải nạp lại Neo4j: `load_primekg.py --reset`.
- **Core dùng `--reload`**: nếu có kết nối SSE (`curl -N …/stream`) đang mở, reload treo ở "Waiting for
  connections to close" — đóng kết nối đó (Ctrl+C).
- **`GET /conversations` yêu cầu query `userId`** (chưa có auth thật) — FE tự gửi; gọi qua `curl`/Swagger
  cần thêm `?userId=user-1`.
- Model LLM trên OpenRouter có thể bị gỡ/đổi tên theo thời gian — nếu gặp 404, kiểm tra lại `AGENT_MODEL`.

## 8. Tài liệu khác

- [`DEPLOY.md`](DEPLOY.md) — deploy production, nạp dữ liệu, xử lý sự cố, vận hành.
- [`core/data-ingest/README.md`](core/data-ingest/README.md) — pipeline dữ liệu theo nguồn.
- [`core/README.md`](core/README.md) — chi tiết code backend (một số phần có thể lệch; ưu tiên
  `docs/kien-truc-he-thong.md` và `core/app/kien-truc-*.md` nếu mâu thuẫn).
- [`core/docs/quy-uoc.md`](core/docs/quy-uoc.md) — quy ước coding backend.
- [`core/docs/db-diagram.md`](core/docs/db-diagram.md) — schema DB.
- [`fe/docs/backend-contract.md`](fe/docs/backend-contract.md) — hợp đồng FE ↔ BE.
