# pipeline/book_ingest — sách giáo khoa → đoạn nội dung theo mục lục

Cài đặt của `docs/plan-toc-chunk-pipeline.md`: lấy khung **part → section → mục** (kèm số trang) từ **mục lục** của sách,
rồi chunk tự do trong khung đó. Mỗi chunk mang metadata của mục chứa nó.

```
PDF → ingest (chữ từng trang) → toc (LLM đọc mục lục, người duyệt) → độ lệch + neo (luật) → chunks → index (Qdrant)
```

| Bước | Module | Ra (trong MinIO `toc/<book>/`) | LLM |
|---|---|---|---|
| ingest | `stages/ingest.py` | `pages.jsonl` | không |
| toc | `stages/toc.py` + `mapping.py` | `toc.auto.json` (máy), `toc.json` (đã áp override + độ lệch + neo) | đọc vài chục trang mục lục |
| chunks | `stages/chunks.py` | `chunks.jsonl`, `review/chunks.json` | không |
| index | `stages/index.py` (+ `BookService`) | `index.json` + các point trong Qdrant | không (embedding local) |

- `toc` **không phụ thuộc** `ingest`: đọc mục lục chỉ OCR riêng vài trang. `mapping.py` (độ lệch + neo) cần `pages.jsonl` nên
  được tính lại mỗi khi sửa mục lục (`reapply`) và ngay trước khi chunk — rất rẻ, không gọi LLM.
- Không chắc thì báo, không đoán im lặng: `suspect` (số trang không tăng dần), `out_of_range`, `anchored=false` → chunk `boundary`.
- Sửa tay lưu ở `overrides/toc.json` nên chạy lại LLM không mất; đổi khung không phải OCR lại.
- Giới hạn: chỉ có những mục mà mục lục liệt kê; một độ lệch duy nhất cho cả sách; số trang OCR sai nhưng vẫn tăng dần chưa bắt được.

## Cách chạy

Không có CLI: dùng giao diện `/admin/toc` (hoặc gọi thẳng API `/api/v1/admin/toc-pipeline/*`). Backend (Core) chạy mỗi bước ở một
thread nền riêng — API trả về ngay, giao diện poll trạng thái; nút Dừng đặt cờ hủy, bước dừng ở điểm kiểm tra gần nhất.
Core khởi động lại giữa chừng thì bước đang chạy được đánh dấu lỗi và làm lại được (bước đọc nội dung có điểm lưu nên không
phải đọc lại các trang đã xong). Backend cần MinIO, Redis và Qdrant đang chạy.

## Chỗ đặt code

`pipeline/` chỉ tập trung vào **logic xử lý/biến đổi dữ liệu** (đọc chữ, đọc mục lục, đối chiếu số trang, chia đoạn, cấu hình sách). Phần còn lại
nằm ở `app/` theo quy ước của Core:

| Việc | Nơi đặt |
|---|---|
| Client + capability generic: MinIO (`MinioClient`), Qdrant (`QdrantVectorClient`), Redis + khoá phân tán (`RedisClient`), LLM trả JSON (`LLMClient`), Docling (`DoclingClient`), embedding (`EmbeddingClient`) | `app/infra/*_client.py` |
| Nghiệp vụ sách trên client generic: CRUD sách, cài đặt, mục lục, chunk, ảnh trang, nhật ký, profile; chunk trong Qdrant (`BookService`) | `app/services/book_service.py` |
| Truy cập dữ liệu sách: `BookRepository`, các bước + phụ thuộc, trạng thái, override, nhật ký, xoá sách | `app/repositories/book_repository.py` |
| Điều khiển pipeline (`BookIngestPipelineService`: kiểm tra, chạy đồng bộ / nền, dừng, duyệt, áp lại override) | `app/services/book_ingest_pipeline_service.py` |
| API / DTO | `app/api/toc_pipeline_api.py`, `app/dto/toc_pipeline.py` |
| **Tạo/giữ/đóng mọi instance** ở trên (`get_book_service()`, `get_book_ingest_pipeline_service()`...) | `app/api/deps.py` |
| Schema cấu hình sách (`Profile`, Pydantic) | `app/models/book_profile.py` |
| MinIO giả cho test | `tests/memory_infra.py` |

Runner nhận client qua constructor và truyền cho từng bước qua `StageContext` (`ctx.llm`, `ctx.docling`, `ctx.embedding`, `ctx.vectors`); bước chỉ
biến đổi dữ liệu, không tự tạo client. Test dựng runner bằng `MemoryMinio` + SQLite file tạm (thay Postgres) + `QdrantClient(":memory:")` + embedding giả (không cần dịch vụ nào chạy).

Trong `pipeline/book_ingest/`: `stages/` (ingest, toc, chunks, index — mỗi bước đọc đầu vào, biến đổi, ghi đầu ra qua `ctx.store`),
`mapping.py` (độ lệch + neo, hàm thuần `build_toc`), `hierarchy.py`, `textutil.py`, `profile.py` (parse/dump cấu hình sách).

## Lưu trữ (không còn workspace trên đĩa)

Mọi thứ nằm trong **MinIO**, bucket `MINIO_BOOKS_BUCKET` (mặc định `derma-books`), dưới `toc/<book_id>/`: `source.pdf`, `page_img/p<N>.png`,
`pages.jsonl`, `toc.auto.json`, `toc.json`, `chunks.jsonl`, `index.json`, `status.json`, `overrides/`, `review/`, `logs/`, `docling_parts/`
(điểm lưu để OCR tiếp tục được). Cache LLM ở `_cache/llm/`. Chunk được embed (local, 384 chiều) và nạp vào **Qdrant** collection
`QDRANT_BOOK_COLLECTION` (mặc định `derma_book_chunks`), payload có `book_id`, part/section/topic, trang, `source_pdf`.

- Chỉ backend (Core) chạm MinIO/Qdrant; FE chỉ gọi API (ảnh trang được Core đọc từ MinIO rồi trả về).
- `status.json` và override được ghi dưới khoá Redis (Core và các thread xử lý cùng ghi). Thư mục tạm chỉ chứa bản sao PDF cho
  pdftotext/Docling/pdftoppm (`/tmp/book_ingest_tmp/<book_id>/`, xoá cùng sách).
- Xoá sách xoá cả đối tượng MinIO lẫn point Qdrant của sách. Chạy lại bước `index` thay thế toàn bộ point cũ của sách.

Test dùng `MemoryMinio` + SQLite + Qdrant in-memory + embedding giả (không cần dịch vụ nào chạy).

Giao diện: `/admin/toc` (API `/api/v1/admin/toc-pipeline/*`). 
Test: `python -m unittest pipeline.book_ingest.tests.test_toc_pipeline pipeline.book_ingest.tests.test_api pipeline.book_ingest.tests.test_storage_index`.
