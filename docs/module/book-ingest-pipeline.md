# Module Pipeline số hoá sách giáo khoa (`document_ingest`)

Admin upload sách PDF, hệ thống đọc chữ, dùng AI đọc **mục lục** làm khung part → section → mục, rồi cắt
chunk trong khung đó và nạp vào Qdrant làm kho tri thức. Mỗi bước phải được người duyệt **approve** thì
bước sau mới chạy.

> Tên file giữ là "book" cho quen, còn code đã đổi hết sang **Document** (`documents`, `DocumentService`,
> `/admin/documents`). Hiện chỉ `type="book"` đi qua pipeline.

## 1. Code nằm ở đâu

| Việc | File |
|---|---|
| FE | `fe/app/admin/documents/page.tsx` (danh sách + upload), `[documentId]/page.tsx` (chi tiết), `fe/features/document-pipeline/` (`api.ts`, `hooks.ts` TanStack Query, `components/` — `StagePanel`, `RunDialog`, `TocEditor`, `ChunkBrowser`, `FigureBrowser`, `PagePreview`, `StageLogDialog`, `SettingsDialog`) |
| API | `core/app/api/document_api.py` (prefix `/api/v1/admin`) |
| Service | `document_service.py` (CRUD, cài đặt, mục lục, chunk, ảnh trang, Qdrant), `document_ingest_pipeline_service.py` (kiểm tra, chạy nền, dừng, duyệt, áp lại) |
| Repository | `document_repository.py` (stateless, nhận `document_id`), `document_override_repository.py` (`repo.overrides`) |
| Model / entity | `models/document.py`, `models/document_stage.py` (`STAGES`), `models/document_profile.py` (`Profile`); entity `dto/base/document.py` |
| Biến đổi dữ liệu | `core/pipeline/document_ingest/` — `stages/{ingest,toc,chunks,index}.py`, `mapping.py`, `hierarchy.py`, `textutil.py`, `profile.py` |
| Client hạ tầng | `app/infra/` — `minio_client`, `qdrant_client`, `llm_client`, `docling_client`, `embedding_client` |

**Ranh giới**: stage chỉ biến đổi dữ liệu, nhận mọi thứ qua `StageContext` (`document_id`, `files`, `meta()`,
`overrides()`, `log()`, `progress()`, `llm`, `docling`, `embedding`, `vectors`), không import service/repository.

## 2. Các bước

```
PDF ──▶ ingest ──────────────┐
        (chữ theo trang)       ├──▶ chunks ──▶ index
PDF ──▶ toc ─────────────────┘   (cắt theo    (embed + Qdrant)
        (LLM đọc mục lục,          khung mục lục)
         người duyệt sửa)
```

| `stage` | Tên trên UI | Phụ thuộc | LLM | Đầu ra (MinIO) |
|---|---|---|---|---|
| `ingest` | Đọc nội dung | — | không | `pages.jsonl`, `figures.json`, `figures/` |
| `toc` | Mục lục | — | **có** | `toc.auto.json` (máy), `toc.json` (đã áp override + độ lệch + neo) |
| `chunks` | Chia đoạn | `ingest`, `toc` | không | `chunks.jsonl`, `review/chunks.json` |
| `index` | Lưu vào kho tri thức | `chunks` | không | `index.json` + point trong Qdrant |

### `ingest`
PDF → mỗi trang một dòng `{page, page_printed, header, text, noise, ...}`. Hai engine (`profile.extraction.engine`):
`pdftotext` (lớp text có sẵn, nhanh) và `docling` (OCR ảnh trang, theo cụm có checkpoint nên dừng giữa chừng
không phải OCR lại). Header lặp và số trang in được tách khỏi `text`.

### `toc`
1. Tìm trang mục lục (người dùng chỉ định, ví dụ `8-22`, hoặc LLM đoán từ các trang đầu/cuối).
2. LLM đọc từng nhóm trang mục lục → danh sách mục: cấp (0 part, 1 section, 2 mục/bệnh, 3 mục con), tên, số trang in.
3. Kiểm tra bằng luật: số trang phải tăng dần, mục phá thứ tự bị đánh `suspect`.
4. `mapping.py` (luật, không LLM) gắn vào trang thật:
   - **Độ lệch**: `trang PDF = trang in + offset`, bỏ phiếu theo các tiêu đề khớp trong thân sách.
   - **Neo**: tìm dòng tiêu đề ở trang kỳ vọng ±1; thấy → `anchored`, không thấy → chỉ biết trang.

`toc` không phụ thuộc `ingest` để người duyệt thử ngay; độ lệch + neo được tính lại khi có `pages.jsonl`.

### `chunks`
Mỗi mục là một vùng `[đầu mục → đầu mục kế tiếp)`, trong vùng cắt tự do theo đoạn/câu tới `max_tokens`
(mặc định 400). Chunk không vượt ranh giới mục có cấp ≤ `boundary_level`. Mỗi chunk mang metadata của mục:
`part`, `section`, `topic`, `subtopic`, `toc_path`, trang PDF / trang in, `boundary` (mục chưa neo được dòng).
Chữ ngoài mọi mục (bìa, lời nói đầu) không thành chunk nhưng được đếm trong summary. Chunk quá dài/ngắn,
`boundary`, mục `suspect` vào hàng đợi xem lại.

### `index`
Embed `context_text` (đường dẫn mục lục + nội dung) bằng embedding qua OpenRouter, nạp vào Qdrant
`derma_document_chunks_v4` (dense + sparse `bm25` cho tìm từ khoá; payload có `document_id`, part/section/topic, trang, vị trí PDF nguồn). Chạy lại
xoá toàn bộ point cũ của tài liệu trước.

Tiền xử lý cho tìm từ khoá (`app/infra/bm25/`): làm sạch chữ OCR (`text_clean`), tách từ ghép tiếng Việt bằng underthesea, bỏ stopword (giữ phủ định và đơn vị liều), stem tiếng Anh bằng Snowball (nltk). Mỗi tài liệu chọn `text_language` (vi / en / mixed) trong cài đặt; giá trị này được ghi vào payload `bm25_mode` để câu hỏi được mã hoá đúng cách cho từng nhóm. Có thêm token bỏ dấu (`~vay`) trọng số thấp để câu hỏi không dấu vẫn khớp. Đổi ngôn ngữ hoặc tokenizer thì phải làm lại bước Lưu vào kho.

## 3. Trạng thái và duyệt

```
not_started ──run──▶ running ──xong──▶ pending_review ──approve──▶ approved
                        │
                        ├── lỗi ──▶ failed
                        └── dừng ─▶ cancelled
bước phía trước chạy lại / áp lại override ──▶ các bước phía sau thành stale
```

- Một bước chỉ chạy được khi mọi bước phụ thuộc đã `approved` (`force` để bỏ qua kiểm tra).
- `run` trả về ngay (202), bước chạy trong **thread nền của Core**; FE poll `GET /admin/documents/{id}`.
- Dừng: đặt cờ huỷ, bước dừng ở điểm kiểm tra gần nhất.
- Core restart giữa chừng: bước đang `running` được đối soát (`reconcile`) thành lỗi, chạy lại được.

### Sửa tay của người duyệt
Lưu trong bảng `document_overrides` (theo `document_id` + `stage_id`), **không ghi đè kết quả máy**: chạy lại
LLM không mất công sửa. Với `toc`, override gồm sửa tên/cấp/trang của mục, `_deleted`, `_added`, `_offset`.
`PATCH /toc` lưu override rồi `reapply` (không gọi LLM) → bước `toc` quay về `pending_review`, bước sau thành `stale`.

## 4. API (`/api/v1/admin`)

| Method | Path | Việc |
|---|---|---|
| GET | `/documents` | danh sách tài liệu |
| POST | `/documents` | upload (multipart: `file`, `title`, `engine?`) |
| GET / DELETE | `/documents/{id}` | chi tiết (kèm trạng thái các bước) / xoá |
| GET / PUT | `/documents/{id}/settings` | cấu hình xử lý (`profile`) |
| POST | `/documents/{id}/stages/{stage}/run` | chạy bước (`options`, `force`) |
| POST | `/documents/{id}/stages/{stage}/cancel` | dừng |
| POST | `/documents/{id}/stages/{stage}/approve` | duyệt |
| POST | `/documents/{id}/stages/{stage}/reapply` | áp lại override |
| GET | `/documents/{id}/stages/{stage}/log` | nhật ký bước |
| GET | `/documents/{id}/pages/{page}`, `.../image` | chữ / ảnh một trang |
| GET / PATCH | `/documents/{id}/toc` | cây mục lục / lưu sửa tay |
| GET | `/documents/{id}/chunks`, `/chunks/export` | xem / xuất chunk |
| GET | `/documents/{id}/figures`, `/figures/{fid}/image` | hình trích từ sách |

Lỗi người dùng sửa được (`StageError`, `InvalidError`) hiển thị nguyên văn trên UI.

## 5. Lưu trữ

| Nơi | Chứa gì |
|---|---|
| **Postgres** | `documents` (metadata, `profile` JSON, `source_file_id`, `pdf_pages`), `document_stages` (state, options, progress, summary, error, thời điểm), `document_overrides`, `files` (dòng cho `source.pdf`) |
| **MinIO** `MINIO_DOCUMENTS_BUCKET` | `document/<id>/`: `source.pdf`, `pages.jsonl`, `toc.auto.json`, `toc.json`, `chunks.jsonl`, `index.json`, `review/`, `logs/`, `page_img/`, `docling_parts/` (checkpoint OCR), `figures/` |
| **Qdrant** | `derma_document_chunks_v4`, một point/chunk |

**Upload**: file stream qua Core vào thư mục tạm, kiểm tra header `%PDF` và ≤ 500 MB, rồi
`DocumentRepository.create` tạo record + một dòng `not_started` cho mỗi bước + ghi file MinIO trong một luồng;
lỗi thì rollback DB và xoá file đã ghi. `<id>` là UUID do DB sinh.

**Xoá**: xoá record (stage, override theo), mọi object MinIO và point Qdrant của tài liệu.

## 6. Kiểm thử

Không cần service thật (MinIO giả + SQLite + Qdrant in-memory + embedding giả):

```bash
cd core && python -m unittest pipeline.document_ingest.tests.test_document_pipeline \
  pipeline.document_ingest.tests.test_api pipeline.document_ingest.tests.test_storage_index
```

## 7. Hạn chế

- Chỉ có những mục mà mục lục liệt kê; một độ lệch duy nhất cho cả sách; số trang OCR sai nhưng vẫn tăng dần
  chưa bắt được.
- Chạy nền bằng thread trong Core (không có hàng đợi job riêng); Core restart thì bước đang chạy phải chạy lại.
- Upload đi qua Core, chưa có presigned upload lên MinIO.
- DB và MinIO không cùng transaction thật; chưa có job dọn object mồ côi khi rollback lỗi.
- Khu admin chưa phân quyền người duyệt.
- Agent chat **chưa có tool tra** collection `derma_document_chunks` — kho tri thức từ sách chưa được dùng khi tư vấn.
- [`core/pipeline/document_ingest/README.md`](../../core/pipeline/document_ingest/README.md) còn nhắc route cũ
  `/admin/toc` và `status.json`; trạng thái bước hiện nằm ở bảng `document_stages`.
