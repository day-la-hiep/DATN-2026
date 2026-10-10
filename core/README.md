# Derma Hospital — Core (`core/`)

Backend của hệ thống: **FastAPI + SQLAlchemy (async) + Alembic**, agent chạy bằng **LangChain `create_agent`** (nền LangGraph) trong một
**tiến trình worker riêng**, giao tiếp qua **RabbitMQ** và **Redis Pub/Sub**; kho tri thức ở **Qdrant** (chunk sách) và **Neo4j**
(PrimeKG + DermO). Bức tranh toàn hệ thống: [`../docs/overview/system-overview.md`](../docs/overview/system-overview.md).

## Cấu trúc

```
core/
├── main.py                 FastAPI app, lifespan (kết nối / đóng hạ tầng, consumer kết quả của agent)
├── app/                    Core API
│   ├── api/                endpoint (conversation, document, upload, health) + deps.py (DI, singleton client / service)
│   ├── services/           nghiệp vụ: conversation, message, document, pipeline ingest, knowledge_base (đọc chunk sách), knowledge_graph
│   ├── repositories/       truy cập Postgres
│   ├── infra/              client hạ tầng: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO, Docling, embedding, LLM
│   ├── models/             ORM (SQLAlchemy) — schema lưu trữ
│   ├── dto/                base/ = entity nghiệp vụ (nguồn chuẩn), common/ = dẫn xuất dùng chung, request/ response/ = hợp đồng API
│   ├── config/ common/ exception/
│   ├── kien-truc-agent.md  kiến trúc agent        kien-truc-memory.md  long-term memory
├── agent/                  Agent Worker (tiến trình riêng): worker, turn, graph/, middleware/, tools/, prompt/, handler/
├── pipeline/document_ingest/  pipeline số hoá sách: PDF → chữ → mục lục → chunk → Qdrant (README riêng)
├── migrations/             Alembic
├── data_ingest/            dữ liệu tĩnh + script nạp Neo4j (PrimeKG, DermO)
└── scripts/                init_db.py (bucket MinIO + dữ liệu mẫu), ...
```

## Chạy dev

Từ gốc repo (xem `makefile`):

```bash
make infra       # Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
cp core/.env.example core/.env
make migrate     # alembic upgrade head
make init-db     # bucket MinIO + dữ liệu mẫu
make backend     # Core http://localhost:3050 (Swagger: /docs)
make worker      # Agent Worker — bắt buộc để agent trả lời
```

Agent cần `AGENT_MODEL` trỏ tới provider đã cấu hình (OpenRouter / DeepSeek / Gemini, xem `app/config/settings.py`) và API key trong `.env`.
Đồ thị tri thức nạp bằng `data_ingest/01_normalize/scripts/load_primekg.py` và `load_dermo.py`; chunk sách do pipeline nạp vào Qdrant
qua giao diện `/admin/documents`.

## Ghi chú

- DB dùng SQLAlchemy **async** (`asyncpg`); pipeline sách chạy trong thread nền nên dùng thêm driver đồng bộ `psycopg`.
- Schema do **Alembic** quản lý: đổi model → `make migrate-new m="mô tả"`, **đọc lại file sinh ra** rồi mới `make migrate`.
- Kiểm tra kiểu: `cd core && .venv/bin/python -m pyright app pipeline agent`.
- Giá trị mặc định trong `.env.example` khớp `docker-compose.yml` ở gốc repo.

## Tài liệu liên quan

- [`app/kien-truc-agent.md`](app/kien-truc-agent.md) — agent: turn, middleware, `ask_user`, event SSE, giới hạn.
- [`app/kien-truc-memory.md`](app/kien-truc-memory.md) — long-term memory.
- [`pipeline/document_ingest/README.md`](pipeline/document_ingest/README.md) — pipeline số hoá sách.
- [`data_ingest/README.md`](data_ingest/README.md) — dữ liệu tĩnh và nạp Neo4j.
- [`../docs/module/chat.md`](../docs/module/chat.md), [`../docs/module/book-ingest-pipeline.md`](../docs/module/book-ingest-pipeline.md) — luồng chat và pipeline.
- [`../docs/overview/db-tables.md`](../docs/overview/db-tables.md) — giải thích từng bảng DB.
- [`../fe/docs/backend-contract.md`](../fe/docs/backend-contract.md) — hợp đồng API (REST + SSE) với Frontend.
