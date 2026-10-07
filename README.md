# Derma Hospital

Đồ án tốt nghiệp: hệ thống hỗ trợ tư vấn da liễu bằng AI, gồm 2 module:

| Module | Người dùng | Làm gì | Tài liệu |
|---|---|---|---|
| **Chat tư vấn da liễu** | bệnh nhân | chat với trợ lý AI (kèm ảnh da). Agent LangGraph suy luận nhiều bước, tra guideline / knowledge graph / phân loại ảnh, hỏi lại khi thiếu thông tin, stream câu trả lời realtime | [docs/module/chat.md](docs/module/chat.md) |
| **Pipeline số hoá sách giáo khoa** | admin | upload PDF → đọc chữ → AI đọc mục lục (người duyệt) → cắt chunk theo mục lục → nạp Qdrant | [docs/module/book-ingest-pipeline.md](docs/module/book-ingest-pipeline.md) |

Tổng quan kiến trúc: [docs/module/overview.md](docs/module/overview.md).

> Kết quả AI chỉ là gợi ý hỗ trợ, **không phải chẩn đoán y khoa**. Guideline đang chờ bác sĩ duyệt.

## 1. Kiến trúc

```
┌──────────────┐  REST + SSE  ┌──────────────────┐  RabbitMQ   ┌───────────────┐
│ FE (Next.js) │─────────────▶│  Core (FastAPI)  │────────────▶│ Agent Worker  │
│ /chats       │◀─────────────│  :3050 /api/v1   │◀────────────│ (LangGraph)   │
│ /admin/...   │              │  + thread nền    │             └───────┬───────┘
└──────────────┘              │  pipeline sách   │◀── Redis Pub/Sub ───┘
                              └───┬──────┬───────┘
        ┌──────────────┬──────────┴┐   ┌─┴─────────┬──────────┐
        │ PostgreSQL   │  MinIO    │   │ Qdrant    │  Neo4j   │
        └──────────────┴───────────┘   └───────────┴──────────┘
```

- **FE** (`fe/`): Next.js App Router. Chat dùng Zustand + SSE; admin dùng TanStack Query và poll trạng thái.
- **Core** (`core/app/`): REST + SSE gateway, là nơi **duy nhất ghi Postgres**. Không gọi LLM cho chat, chỉ
  publish turn sang Worker và forward nguyên văn event từ Redis ra SSE. Pipeline sách chạy trong thread nền.
- **Agent Worker** (`core/agent/`): tiến trình riêng, consume `agent_request_queue`, chạy `create_agent`
  (LangChain/LangGraph) với tool + middleware, gọi LLM qua OpenRouter, trả kết quả về `agent_response_queue`.
- **Pipeline** (`core/pipeline/document_ingest/`): chỉ biến đổi dữ liệu (`ingest → toc → chunks → index`).
- **Hạ tầng**: Postgres (dữ liệu nghiệp vụ), Redis (Pub/Sub + key turn), RabbitMQ (Core ⇄ Worker),
  Qdrant (guideline, chunk sách), Neo4j (PrimeKG + DermO), MinIO (ảnh đính kèm, file tài liệu).

## 2. Cấu trúc thư mục

```
fe/                      Next.js
  app/                   route: /chats, /admin/documents
  features/chat/         store Zustand, types, components chat
  features/document-pipeline/  api, hooks TanStack Query, components admin
  services/              HTTP client, SSE, adapter wire ↔ UI
  components/ui/         UI primitive
core/
  main.py                entrypoint Core
  app/                   api → services → repositories → models; dto/{base,request,response}; infra/
  agent/                 worker.py, turn.py, graph/, tools/, middleware/, prompt/
  pipeline/document_ingest/   stages/, mapping.py, tests/
  migrations/            Alembic
  data_ingest/           dữ liệu guideline / KG và script nạp
docs/module/             tài liệu từng module
docker-compose.yml       hạ tầng dev
docker-compose.prod.yml  stack production (xem DEPLOY.md)
```

## 3. Chạy dev

Yêu cầu: Docker Compose v2, Python 3.12+ và [`uv`](https://docs.astral.sh/uv/), Node.js 20+ và `pnpm`,
API key OpenRouter.

```bash
cp core/.env.example core/.env          # điền OPENROUTER_API_KEY (+ TAVILY_API_KEY nếu dùng web search)
cp fe/.env.local.example fe/.env.local  # NEXT_PUBLIC_USE_MOCK=false để gọi Core thật

make infra       # docker compose up -d: Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO
make migrate     # alembic upgrade head
make init-db     # bucket MinIO + dữ liệu mẫu (user-1, bác sĩ, admin) — chạy sau migrate
make backend     # Core http://localhost:3050 (Swagger: /docs)
make worker      # Agent Worker — bắt buộc để agent trả lời
make frontend    # FE http://localhost:3000
```

**Nạp dữ liệu đồ thị tri thức** (Neo4j mới tạo đang trống; chunk sách vào Qdrant qua giao diện `/admin/documents`), chạy trong `core/`:

```bash
uv run python data_ingest/01_normalize/scripts/load_primekg.py          # PrimeKG → Neo4j
uv run python data_ingest/01_normalize/scripts/load_dermo.py            # DermO → Neo4j
```

Thêm `--reset` để xoá dữ liệu cũ trước khi nạp. Chi tiết nguồn dữ liệu: [core/data_ingest/README.md](core/data_ingest/README.md).

Tool `classify_skin_image` cần checkpoint CNN tại `SKIN_CNN_CHECKPOINT_PATH`.

### Biến môi trường chính

| Biến | Dùng cho |
|---|---|
| `DATABASE_URL`, `REDIS_*`, `RABBITMQ_URL`, `QDRANT_URL`, `NEO4J_*`, `MINIO_*` | kết nối hạ tầng, mặc định khớp `docker-compose.yml` |
| `AGENT_MODEL`, `AGENT_TEMPERATURE`, `OPENROUTER_API_KEY` | model mặc định của agent |
| `TAVILY_API_KEY` | tool tra web nguồn uy tín |
| `APP_ACCESS_TOKEN` | token dùng chung cho app (rỗng = tắt); FE nhập ở màn access gate |
| `NEXT_PUBLIC_USE_MOCK`, `NEXT_PUBLIC_API_URL` | FE dùng mock hay Core thật, URL Core |

`.env` không được commit.

## 4. Kiểm tra

```bash
cd core && .venv/bin/python -m pyright app pipeline     # kiểu Python
cd core && python -m unittest pipeline.document_ingest.tests.test_document_pipeline \
  pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index
cd fe && pnpm exec tsc --noEmit && pnpm lint
```

Test pipeline không cần service thật (MinIO giả + SQLite + Qdrant in-memory).

## 5. Quy ước

Chi tiết trong các skill ở `.claude/skills/`; dưới đây là các điểm hay nhầm.

| Khu vực | Skill |
|---|---|
| `core/app/`, `core/agent/` (endpoint, DTO, model, service, tool, middleware, prompt) | [derma-core-conventions](.claude/skills/derma-core-conventions/SKILL.md) |
| `core/pipeline/document_ingest/`, `app/services/document_*.py`, `document_repository.py` | [derma-pipeline-conventions](.claude/skills/derma-pipeline-conventions/SKILL.md) |
| `fe/` (trang, component, store, hook, SSE event) | [derma-fe-conventions](.claude/skills/derma-fe-conventions/SKILL.md) |
| Chạy Core / Worker, gửi tin thử, pyright | [run-core](.claude/skills/run-core/SKILL.md) |
| Chạy FE, chụp màn hình | [run-fe](.claude/skills/run-fe/SKILL.md) |
| Thử prompt / model / tool của agent | [experiment-agent-flow](.claude/skills/experiment-agent-flow/SKILL.md) |

**Backend**
- Phân lớp `api` (chỉ map request/response) → `services` (nghiệp vụ) → `repositories` (stateless, nhận id trực
  tiếp) → `models` (ORM).
- Entity nghiệp vụ ở `app/dto/base/`, tách khỏi ORM (`app/models/`) và DTO wire (`app/dto/request|response/`).
  Đổi `dto/base` phải được duyệt trước rồi mới cascade xuống model/repo/service.
- Wire dùng snake_case, response bọc `{"data": ...}`.
- Chỉ Core ghi Postgres; Worker trả kết quả qua RabbitMQ.
- `pipeline/` không import `app.services` / `app.repositories`; stage nhận mọi thứ qua `StageContext`.
  Lỗi người dùng sửa được dùng `StageError` / `InvalidError` (hiển thị nguyên văn trên UI).
- Schema đổi qua Alembic (`make migrate-new m="..."`), **đọc lại file sinh ra**, không để autogenerate drop bảng có dữ liệu.
- Python snake_case; docstring và comment tiếng Việt, giải thích **vì sao**.

**Frontend**
- `app/` chỉ là route mỏng; logic theo tính năng nằm ở `features/<feature>/`; gọi HTTP ở `services/`.
- Chat: state trong Zustand store, event SSE được chuẩn hoá trong `store.ts`. Admin: TanStack Query hooks.

## 6. Hạn chế đã biết

- Chưa có auth đa người dùng: chat truyền `user_id` từ client, admin chỉ dùng app token.
- Checkpointer và long-term memory của agent đang in-memory → mất khi restart Worker, chỉ chạy được 1 Worker.
- Mỗi hội thoại một turn một lúc (không có Steer); đang chờ trả lời câu hỏi thì không gửi được tin mới.
- Upload PDF đi qua Core; DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi.
- Chunk sách đã nạp Qdrant nhưng agent chat chưa có tool tra collection này.
- Tư vấn bác sĩ / video call mới có schema DB.

## 7. Tài liệu khác

- [DEPLOY.md](DEPLOY.md) — deploy production bằng Docker Compose (hiện mới mô tả phần chat).
- [core/app/kien-truc-agent.md](core/app/kien-truc-agent.md), [core/app/kien-truc-memory.md](core/app/kien-truc-memory.md) —
  thiết kế agent và memory (một phần mô tả thiết kế cũ; khi lệch, ưu tiên `docs/module/`).
- [core/pipeline/document_ingest/README.md](core/pipeline/document_ingest/README.md) — chi tiết pipeline.
