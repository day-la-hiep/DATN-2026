# Báo cáo nhánh `feat/rag-optimize`

Nhánh tối ưu phần truy xuất tri thức (RAG) của trợ lý da liễu: đưa tìm kiếm sách giáo khoa lên mức lai (semantic + từ khoá + đồ thị tri thức), xếp hạng lại bằng reranker, hỗ trợ tiếng Việt và tiếng Anh, và đổi sang embedding/reranker chất lượng cao hơn.

## 1. Kiến trúc truy xuất hiện tại

```
câu hỏi ─► LLM trích thực thể y khoa (tên Anh + tên Việt)
             ├─► Semantic: embedding Qwen3 ─► Qdrant (dense)        ─ 20 đoạn ─┐
             ├─► BM25: query mở rộng Việt–Anh ─► Qdrant (sparse)    ─ 20 đoạn ─┴─► RRF, giữ 20 ─┐
             └─► Đồ thị tri thức (PrimeKG / DermO, Neo4j)  ─ các câu quan hệ / bệnh ứng viên ──────┤
                                                                                                    ▼
                                         Qwen3-Reranker chấm (câu hỏi, đoạn) ─► top_k kèm nguồn (sách, mục, trang)
```

Tool mặc định của agent là `hybrid_retrieval`; ba tool chuyên biệt `semantic_search`, `keyword_search`, `knowledge_graph_search` dùng khi đã biết cần loại thông tin nào. Kết quả luôn kèm nguồn trích dẫn và ghi rõ chỉ là gợi ý, không phải chẩn đoán.

## 2. Những việc đã làm

### 2.1 Truy xuất lai và đồ thị tri thức
- `hybrid_retrieval` chạy song song ba nhánh (semantic, BM25, KG) rồi trộn bằng RRF và rerank (`agent/tools/hybrid_retrieval/`).
- Nhánh KG: LLM trích thực thể và dịch sang tiếng Anh y khoa, tra quan hệ PrimeKG/DermO và bệnh ứng viên (`kg.py`, `knowledge_graph_service.py`, `neo4j_client.py`).
- Nhánh lỗi không làm hỏng cả lượt: tool báo trong `notes` và dùng phần còn lại.

### 2.2 Tìm từ khoá BM25 ngay trong Qdrant
- Chuyển BM25 từ chỉ mục trong bộ nhớ sang **sparse vector trong Qdrant** (Qdrant tính IDF), collection có dense và sparse `bm25` (`app/infra/bm25/sparse.py`).
- Chấm điểm theo công thức BM25 (`k1=1.2`, `b=0.75`).

### 2.3 Hỗ trợ tiếng Việt và tiếng Anh
- **Mở rộng query Việt–Anh**: bước trích thực thể trả thêm tên tiếng Việt chuẩn (`vi`); query BM25 được nối với tên Anh và Việt của thực thể, nên "vảy nến mảng" bắt được cả đoạn sách ghi "plaque psoriasis". Dùng chung một lần gọi LLM với nhánh KG.
- **Tiền xử lý văn bản** (`app/infra/bm25/`, `app/infra/text_clean.py`):
  - làm sạch nhiễu OCR/PDF: nối từ gạch nối cuối dòng, bỏ ký tự điều khiển, chuẩn hoá nháy/gạch, đổi chữ Hy Lạp (α → alpha);
  - tiếng Việt: tách từ ghép bằng underthesea, giữ cả từ ghép lẫn âm tiết (`điều_trị`, `điều`, `trị`) vì cách tách đổi theo ngữ cảnh;
  - tiếng Anh: stemming Snowball (nltk), `databases` khớp `database`;
  - bỏ stopword, nhưng **giữ từ phủ định và đơn vị/liều** vì mang nghĩa lâm sàng; nguồn stopword hardcode `builtin`, có sẵn đường mở rộng sang corpus nltk (`stopwords.py`);
  - thêm token bỏ dấu `~vay` (trọng số thấp 0.3 ở câu hỏi) để câu hỏi gõ không dấu vẫn khớp;
  - thuật ngữ như `il-17`, `5-fu` giữ nguyên cụm và thêm các phần con.
- **Chọn ngôn ngữ theo tài liệu**: `Profile.indexing.text_language` ∈ {`vi`, `en`, `mixed`} (mặc định `mixed`), chọn trong hộp "Cài đặt sách" ở `/doctor/documents`. Sách thuần Anh bỏ qua underthesea để lưu nhanh hơn. Mỗi point ghi payload `bm25_mode`, lúc tìm kiếm câu hỏi được mã hoá theo từng mode rồi lọc đúng nhóm, nên mọi tài liệu được khớp đối xứng.

### 2.4 Embedding và reranker Qwen3 qua OpenRouter
- Embedding: `qwen/qwen3-embedding-8b` (4096 chiều), gọi `POST /embeddings`, có prefix `Instruct:` cho câu hỏi theo cách Qwen3 được huấn luyện (`agent/common/embeddings.py`).
- Reranker: `qwen/qwen3-reranker-8b`, gọi `POST /rerank` (`reranker.py`); ngưỡng đoạn đưa vào rerank tăng lên 3000 ký tự.
- Mô hình và số chiều chỉnh qua `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RERANKER_MODEL`. Lỗi reranker thì tự dùng thứ tự RRF.
- Collection Qdrant mặc định: `derma_document_chunks_v4`.
- Đã thử gọi thật: embedding trả 4096 chiều, rerank xếp đúng thứ tự (đoạn liên quan 0.98, không liên quan ≈ 0).
- Trước đó đã thử `BAAI/bge-m3` chạy local; bỏ vì chuyển sang API.

### 2.5 Hạ tầng đi kèm
- **Ingest Worker** (`app/workers/document_ingest_worker.py`): chạy các bước pipeline số hoá sách ở tiến trình riêng qua RabbitMQ, dừng qua Redis.
- Logging toàn hệ thống (`app/config/log.py`), bộ script thử agent (`agent/test/`: `try_retrieval.py`, `try_reasoning.py`, ...).
- Tổ chức lại agent: `context/`, `common/`, `publisher.py`, `app/workers/agent_response_consumer.py`.

## 3. Cấu hình và triển khai
- `OPENROUTER_API_KEY` dùng chung cho LLM, embedding và reranker (xem `core/.env.example`).
- Thêm phụ thuộc `nltk`, `underthesea`; không còn bake model embedding local trong `Dockerfile`.
- `makefile`: `make ingest-worker` chạy Ingest Worker.

## 4. Kiểm thử
- Test mới `pipeline/document_ingest/tests/test_text_preprocess.py`: làm sạch, tokenizer vi/en, stopword, không gọi underthesea khi `en`, tìm đúng tài liệu theo `bm25_mode`.
- Lần chạy gần nhất: pyright sạch; 47 test pipeline pass; `tsc` của FE sạch.
- **Chưa làm**: đo recall trên dữ liệu thật; chưa thử giao diện trên trình duyệt.

## 5. Việc cần làm sau khi nhận nhánh
1. Đặt `OPENROUTER_API_KEY`; để trống `QDRANT_LEGACY_BOOK_COLLECTION` (collection cũ khác số chiều).
2. **Index lại sách**: collection `v4` đang trống, và sparse vector cũ dùng tokenizer cũ. Chọn ngôn ngữ trong Cài đặt sách rồi chạy lại bước `index` ở `/doctor/documents`.
3. Đo thử bằng `agent/test/try_retrieval.py`: "vảy nến mảng", "treatments for psoriasis", "IL-17", "methotrexate chống chỉ định".

## 6. Hạn chế đã biết (ghi vào báo cáo đồ án)
- Văn bản sách và câu hỏi được gửi tới OpenRouter (embedding, rerank), không còn xử lý hoàn toàn nội bộ.
- underthesea tách từ chậm hơn regex; index cả cuốn sách mất vài phút. Cách tách từ ghép phụ thuộc ngữ cảnh nên có thể lệch giữa câu hỏi ngắn và đoạn dài (đã giảm nhẹ bằng cách giữ thêm âm tiết).
- Query không dấu ("vay nen") khớp nhờ token bỏ dấu trọng số thấp (0.3), nên có thể kéo thêm đoạn chứa từ khác nghĩa cùng gốc (ma / má / mạ) ở thứ hạng thấp.
- Các việc còn lại cho nhánh đồ thị tri thức: xem [pending/knowledge-graph.md](../pending/knowledge-graph.md).
- Embedding 4096 chiều tốn dung lượng Qdrant hơn các model nhỏ; có thể dùng bản 4B (2560 chiều) nếu cần nhẹ hơn.
- Chất lượng mở rộng query và trích thực thể phụ thuộc model `AGENT_MODEL`.
- Chưa có cơ chế ngưỡng điểm: `hybrid_retrieval` luôn trả đủ `top_k`, agent tự nhìn `score`.
- Kết quả AI chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa.
