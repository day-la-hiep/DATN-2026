# AGENTS.md — Derma Hospital

Hướng dẫn cho Agent / Gemini khi làm việc trong repo này.

## 0. Bối cảnh & phạm vi

- Đây là **đồ án tốt nghiệp**, không phải sản phẩm production. Ưu tiên: đúng nghiệp vụ, flow đi thông
  suốt từ đầu đến cuối, dễ giải thích khi bảo vệ. Không cần tối ưu hiệu năng, hardening, scale,
  hay viết test phủ kín.
- Vẫn giữ những thứ không thương lượng: không để lộ secret, không commit `.env`, không làm hỏng dữ liệu
  đã nhập (migration phải giữ dữ liệu), và kết quả AI luôn ghi rõ **không phải chẩn đoán y khoa**.
- Nếu cần chọn giữa "làm gọn để demo chạy được" và "làm đúng kiến trúc lớn", ưu tiên cái chạy được
  và giải thích được, rồi ghi chú phần còn thiếu.

## 1. Repo gồm 2 hệ thống

| Hệ thống | Mô tả | Đọc thêm |
|---|---|---|
| **Chat tư vấn da liễu** | FE chat + Core API + Agent Worker (LangGraph) tra guideline, knowledge graph, phân loại ảnh da | `README.md`, `docs/kien-truc-he-thong.md`, `core/app/kien-truc-agent.md` |
| **Pipeline số hoá sách giáo khoa** (`document_ingest`) | Admin upload PDF → OCR/đọc chữ → AI đọc mục lục (người duyệt) → cắt chunk theo mục lục → nạp Qdrant | `core/pipeline/document_ingest/README.md` |

Cấu trúc thư mục:

```
fe/        Next.js App Router: /chats (chat), /doctor (bác sĩ xem báo cáo AI), /admin/documents (pipeline admin)
core/      FastAPI (app/), agent LangGraph (agent/), pipeline (pipeline/document_ingest/),
           migrations Alembic (migrations/), dữ liệu nạp (data_ingest/)
docs/      tài liệu kiến trúc + hướng dẫn chung
docker-compose.yml   hạ tầng dev (Postgres, Redis, RabbitMQ, Qdrant, Neo4j, MinIO)
```

## 2. Chạy dự án

```bash
make infra          # docker compose up -d (hạ tầng)
make migrate        # alembic upgrade head
make backend        # Core FastAPI :3050 (hoặc python main.py)
make worker         # Agent Worker (tiến trình riêng, consume RabbitMQ)
make frontend       # Next.js :3000
```

- Python dùng `uv` (`core/pyproject.toml`), venv tại `core/.venv`. Chạy script trong `core/`.
- Test pipeline (không cần service thật, dùng MinIO giả + SQLite + Qdrant in-memory):
  ```bash
  cd core && python -m unittest pipeline.document_ingest.tests.test_document_pipeline \
    pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index
  ```
- Kiểm tra kiểu: `cd core && .venv/bin/python -m pyright app pipeline`.
- Migration mới: `make migrate-new m="mô tả"`, rồi **đọc lại file sinh ra** trước khi chạy. Không để
  autogenerate drop/create bảng có dữ liệu.

## 3. Luồng nghiệp vụ chính

### 3.1 Chat tư vấn
1. FE gửi tin nhắn tới Core (REST) → Core ghi `messages`, publish "turn request" lên RabbitMQ.
2. Agent Worker chạy LangGraph (Turn → Step → Reasoning), gọi tool (guideline, KG, ảnh), publish
   từng bước lên Redis Pub/Sub.
3. Core forward nguyên văn event qua SSE (`/conversations/{id}/stream`) cho FE hiển thị realtime.
4. Kết quả cuối quay về Core qua RabbitMQ, Core ghi Postgres. Chỉ Core ghi Postgres.
5. Khi thiếu thông tin, agent dùng `interrupt()` để hỏi người dùng; người dùng trả lời để resume.

### 3.2 Pipeline số hoá sách (admin)
Các bước theo thứ tự, mỗi bước phải được người duyệt **approve** trước khi bước sau chạy:

| Bước (`stage`) | Làm gì | LLM |
|---|---|---|
| `ingest` | PDF → chữ theo trang (`pages.jsonl`) | không |
| `toc` | AI đọc trang mục lục → cây mục; người duyệt sửa qua override | có |
| `chunks` | cắt đoạn theo khung mục lục (`chunks.jsonl`) | không |
| `index` | embedding local + nạp Qdrant | không |

- Trạng thái: `not_started → running → pending_review → approved`; `failed`/`cancelled`; `stale`
  khi bước phía trước chạy lại. Thứ tự và phụ thuộc: `app/models/document_stage.py::STAGES`.
- Chạy nền bằng thread trong Core; FE poll `GET /admin/documents/{id}` để xem tiến độ.
- Sửa tay của người duyệt lưu trong `document_overrides` (không ghi đè kết quả máy).

### 3.3 Lưu trữ tài liệu
- **Postgres**: record `documents` (metadata + cột `profile` JSON), `document_stages`,
  `document_overrides`.
- **MinIO** (bucket `MINIO_DOCUMENTS_BUCKET`): mọi file của một tài liệu nằm dưới `document/<id>/`
  (`source.pdf`, `pages.jsonl`, `toc.json`, `chunks.jsonl`, `logs/`...). `<id>` là UUID do DB sinh.
- **Qdrant**: một point cho mỗi chunk, payload có `document_id`.
- Upload: file đi qua Core (stream vào thư mục tạm, kiểm tra `%PDF` và kích thước ≤ 500 MB), rồi
  `DocumentRepository.create` ghi record + file trong một luồng, lỗi thì rollback DB và xoá file.

## 4. Kiến trúc & quy ước cần nhớ

- **Entity nghiệp vụ** ở `core/app/dto/base/` (`Document`, `File`, `ProcessStage`, `DocumentChunk`, ...)
  khác với ORM (`app/models/`) và DTO wire (`app/dto/request|response/`). **Đổi `dto/base` phải hỏi
  người dùng duyệt trước** rồi mới cascade sang models/repo/service.
- **Repository là stateless**: `DocumentRepository` nhận `document_id` trực tiếp. Override nằm ở
  `DocumentOverrideRepository` (field `repo.overrides`). Không có object "mở sẵn 1 tài liệu".
- **`pipeline/` chỉ làm biến đổi dữ liệu.** Stage nhận `StageContext` (`document_id`, `files`,
  `meta()`, `overrides()`, `log()`, `progress()`), không import `app.services`/`app.repositories`.
- **Service** (`DocumentService`, `DocumentIngestPipelineService`) điều phối nghiệp vụ;
  **API** (`app/api/document_api.py`) chỉ map request/response.
- Route admin: `/api/v1/admin/documents/*`, mục lục của một tài liệu ở `/documents/{id}/toc`.
  Stage `toc` và `toc.json` là dữ liệu mục lục, tên đó đúng — đừng đổi.
- Lỗi người dùng sửa được → `StageError` / `InvalidError` (hiển thị nguyên văn trên UI).
- Tên và comment: Python dùng snake_case; docstring và comment **tiếng Việt**, giải thích **vì sao**,
  không mô tả **cái gì** đã rõ trong code. Không viết docstring nhiều đoạn.

## 5. Kỹ năng & quy ước thư mục

Khi làm việc trong một khu vực, tham khảo các quy ước chi tiết:
- `core/app/`: endpoint, DTO, model, service, tool, middleware, prompt agent.
- `core/pipeline/document_ingest/`: quy ước pipeline xử lý PDF, OCR, chunking, indexing.
- `fe/`: trang Next.js, component, hook, store, SSE event.

Quy tắc dùng chung:
- Quy ước `dto/base` (entity nghiệp vụ) nằm trong `derma-core-conventions`; đổi `dto/base` vẫn phải hỏi duyệt trước.
- Khi có mâu thuẫn giữa các tài liệu, hướng dẫn chuyên biệt cho từng module được ưu tiên.
- Nếu đổi quy ước (tên module, route, cấu trúc thư mục), cập nhật tài liệu tương ứng cùng lúc với code.

## 6. Việc hay làm trong đồ án

- Thêm một **nghiệp vụ mới** thường là: entity/DTO (`dto/base` — hỏi trước) → model + migration →
  repository → service → endpoint → màn hình FE. Làm trọn một flow rồi mới mở rộng.
- Khi demo, dữ liệu mẫu nằm ở `core/data_ingest/` và script `reset-and-gen-data.sh`.
- Ghi chú các điểm **chưa làm / đơn giản hoá có chủ ý** (ví dụ: DB và MinIO không cùng transaction
  thật, không có tài liệu người dùng đăng nhập theo quyền, chưa có job dọn file mồ côi) vào mục
  "Hạn chế" khi viết báo cáo, không cần sửa ngay.

## 7. Hạn chế đã biết (đồ án)

- Không có auth đa người dùng cho khu admin (chỉ dùng app token).
- Upload PDF đi qua Core; chưa có presigned upload trực tiếp lên MinIO.
- Không có job dọn object MinIO mồ côi khi rollback thất bại.
- Chưa có tài liệu hướng dẫn triển khai cho pipeline; `DEPLOY.md` chỉ mô tả chat.
- Kết quả AI chỉ là gợi ý hỗ trợ, không phải chẩn đoán; guideline đang chờ bác sĩ duyệt.

## 8. Khi làm việc với Agent / Gemini

- Trả lời ngắn gọn, bằng tiếng Việt. Thuật ngữ kỹ thuật giữ nguyên tiếng Anh.
- Thay đổi nhỏ, rõ ràng: sửa đúng chỗ cần sửa, không refactor kèm theo.
- Trước khi báo "xong": chạy pyright + test liên quan (backend) hoặc `pnpm tsc --noEmit` (frontend). Với thay đổi UI, nói rõ nếu chưa test trên trình duyệt.
- Không tự commit, không push, không chạy lệnh huỷ dữ liệu (`docker compose down -v`, xoá bucket, `DROP`)
  nếu chưa được hỏi.
