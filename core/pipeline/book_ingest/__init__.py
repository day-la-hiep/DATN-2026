"""book_pipeline — sách PDF → chunk có metadata theo MỤC LỤC (part → section → mục), lưu vào MinIO + Qdrant.

Luồng: ingest (chữ từng trang) → toc (LLM đọc mục lục, người duyệt) → độ lệch + neo (luật) → chunks.
Xem `docs/plan-toc-chunk-pipeline.md`. Chạy bằng giao diện `/admin/toc` qua API `/api/v1/admin/toc-pipeline/*`: backend thực hiện mọi bước (không có CLI),
dữ liệu nằm trong MinIO + Qdrant."""
