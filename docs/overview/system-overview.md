# Tổng quan hệ thống Derma Hospital

Derma Hospital gồm **2 module nghiệp vụ** dùng chung một Core (FastAPI) và một bộ hạ tầng:

| Module | Người dùng | Làm gì | Tài liệu |
|---|---|---|---|
| **Chat tư vấn da liễu** | bệnh nhân | chat với trợ lý AI (kèm ảnh da); agent suy luận nhiều bước, tra guideline / knowledge graph / ảnh, hỏi lại khi thiếu thông tin | [chat.md](chat.md) |
| **Pipeline số hoá sách giáo khoa** (`document_ingest`) | admin | upload PDF → đọc chữ → AI đọc mục lục (người duyệt) → cắt chunk theo mục lục → nạp Qdrant | [book-ingest-pipeline.md](book-ingest-pipeline.md) |

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**.

## 1. Thành phần

```
┌──────────────┐  REST + SSE  ┌──────────────────┐  RabbitMQ   ┌───────────────┐
│ FE (Next.js) │─────────────▶│  Core (FastAPI)  │────────────▶│ Agent Worker  │
│ /chats       │◀─────────────│  :3050 /api/v1   │◀────────────│ (LangGraph)   │
│ /admin/...   │              │                  │             └───────┬───────┘
└──────────────┘              │  + thread nền    │                     │ publish event
                              │  pipeline tài liệu│◀──── Redis Pub/Sub ─┘
                              └───┬──────┬───────┘
                                  │      │
        ┌──────────────┬──────────┴┐   ┌─┴─────────┬──────────┐
        │ PostgreSQL   │  MinIO    │   │ Qdrant    │  Neo4j   │
        │ (chỉ Core ghi)│ file/ảnh │   │ vector    │  KG      │
        └──────────────┴───────────┘   └───────────┴──────────┘
```

| Thành phần | Vai trò | Vị trí code |
|---|---|---|
| **FE** | Next.js App Router. `/chats` (Zustand store + SSE), `/doctor/documents` (TanStack Query, poll) | `fe/app/`, `fe/features/chat/`, `fe/features/document-pipeline/` |
| **Core** | REST + SSE gateway, ghi Postgres, publish turn sang Worker, consume kết quả; chạy pipeline tài liệu trong thread nền | `core/app/` (`api/`, `services/`, `repositories/`, `models/`, `dto/`, `infra/`) |
| **Agent Worker** | Tiến trình riêng, consume `agent_request_queue`, chạy agent LangGraph, stream event lên Redis | `core/agent/` (`worker.py`, `turn.py`, `graph/`, `tools/`, `middleware/`) |
| **Pipeline tài liệu** | Chỉ biến đổi dữ liệu (PDF → trang → mục lục → chunk → vector) | `core/pipeline/document_ingest/` |
| **PostgreSQL** | Nguồn sự thật: user, hồ sơ bệnh nhân, hội thoại, tin nhắn, file, tài liệu + trạng thái bước | migration Alembic `core/migrations/` |
| **Redis** | Pub/Sub event realtime của chat; key turn đang chạy / turn chờ đẩy | `app/infra/redis_client.py` |
| **RabbitMQ** | `agent_request_queue` (Core → Worker), `agent_response_queue` (Worker → Core) | `app/infra/rabbitmq_client.py` |
| **Qdrant** | `derma_document_chunks_v4` (chunk sách do pipeline nạp, agent tìm bằng `hybrid_retrieval` (hoặc `semantic_search` / `keyword_search`)) | `app/infra/qdrant_client.py` |
| **Neo4j** | PrimeKG lọc da liễu (`:Entity`) + ontology DermO (`:DermoTerm`) | nạp từ `core/data_ingest/` |
| **MinIO** | ảnh đính kèm tin nhắn; mọi file của tài liệu dưới `document/<id>/` | `app/infra/minio_client.py` |

## 2. Nguyên tắc kiến trúc chung

- **Chỉ Core ghi Postgres.** Worker gửi kết quả về qua `agent_response_queue`; pipeline ghi trạng thái qua
  repository của Core.
- **Core không gọi LLM cho chat** — chỉ publish turn và forward event. LLM chạy ở Worker, nên request HTTP luôn
  trả nhanh. (Pipeline tài liệu có gọi LLM ở bước `toc`, nhưng chạy trong thread nền, API vẫn trả ngay.)
- **Phân lớp trong `core/app/`**: `api` (map request/response) → `services` (nghiệp vụ) → `repositories`
  (truy cập DB, stateless) → `models` (ORM). Entity nghiệp vụ nằm ở `dto/base/`, khác DTO wire
  (`dto/request|response/`) và ORM.
- **`pipeline/` không import `app.services`/`app.repositories`** — nhận mọi thứ qua `StageContext`.
- Wire dùng **snake_case**, envelope `{"data": ...}`.

## 3. Dữ liệu chính (Postgres)

| Nhóm | Bảng |
|---|---|
| Người dùng | `users`, `patient_profiles`, `doctors`, `admins` |
| Chat | `conversations`, `messages` (cột `metadata` JSONB: reasoning, choice, ...), `files`, `message_files` |
| Tư vấn bác sĩ (mới có schema) | `consultation_sessions`, `video_calls` |
| Tài liệu | `documents` (+ cột `profile` JSON), `document_stages`, `document_overrides` |

Chi tiết: [`core/docs/db-diagram.md`](../../core/docs/db-diagram.md).

## 4. Chạy dự án

```bash
make infra     # docker compose: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
make migrate   # alembic upgrade head
make init-db   # bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin)
make backend   # Core :3050
make worker    # Agent Worker
make frontend  # Next.js :3000
```

Guideline/KG phải được nạp trước thì agent mới tra cứu được (`core/data_ingest/`).

## 5. Tài liệu liên quan

- [`core/docs/api-doc.md`](../../core/docs/api-doc.md), [`openapi.yaml`](../../core/docs/openapi.yaml) — REST.
- [`core/docs/async-api-doc.md`](../../core/docs/async-api-doc.md), [`asyncapi.yaml`](../../core/docs/asyncapi.yaml) — SSE.
- [`core/app/kien-truc-agent.md`](../../core/app/kien-truc-agent.md), [`kien-truc-memory.md`](../../core/app/kien-truc-memory.md).
- [`core/pipeline/document_ingest/README.md`](../../core/pipeline/document_ingest/README.md).

## 6. Hạn chế chung (đồ án)

- Chưa có auth đa người dùng: chat truyền `user_id` từ client, khu admin chưa phân quyền.
- Checkpointer và long-term memory của agent đang in-memory → mất khi restart Worker, chỉ chạy được 1 Worker.
- DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi.
- Schema tư vấn bác sĩ / video call đã có nhưng chưa có API và màn hình.
- Chunk sách đã nạp Qdrant nhưng agent chat **chưa có tool tra** collection `derma_document_chunks`.
