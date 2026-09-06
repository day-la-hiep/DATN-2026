# Long-term memory — Qdrant + distill bằng LLM

Xem [`kien-truc-agent.md`](./kien-truc-agent.md) cho vòng lặp Turn/Step/Reasoning — tài liệu
này chỉ mô tả lớp memory PHỤ TRỢ nằm ngoài 1 turn.

## 0. Vấn đề cần giải quyết

Trước khi có cơ chế này, Agent **không nhớ gì ngoài phạm vi 1 turn**:
`worker.py::_initial_state()` build `messages` chỉ từ đúng 1 `HumanMessage` (nội dung tin nhắn
hiện tại). Kể cả 2 turn liên tiếp trong CÙNG 1 hội thoại, turn sau không thấy turn trước —
LangGraph checkpointer dùng `thread_id = message_id` của TỪNG turn (không phải
`conversation_id`), nên state không tự nối giữa các turn.

## 1. Thiết kế: 1 cơ chế duy nhất cho cả 2 phạm vi

Thay vì tách riêng "nhớ trong hội thoại" và "nhớ xuyên hội thoại", cả 2 dùng **chung 1 cơ chế**:
mỗi turn hoàn tất được tóm tắt (distill) thành 1 "memory" ngắn gọn, gắn `user_id`, lưu vector
vào Qdrant; turn mới nào cũng semantic-search theo `user_id` (không lọc theo `conversation_id`)
để lấy memory liên quan nhất — bất kể memory đó đến từ hội thoại nào. Vì vậy 1 memory từ turn
trước TRONG CÙNG hội thoại tự nhiên xuất hiện lại (nếu liên quan) y hệt cách 1 memory từ hội
thoại khác xuất hiện — không cần logic riêng cho từng phạm vi.

**Đánh đổi có chủ đích**: memory là bản tóm tắt (lossy), KHÔNG phải replay nguyên văn hội thoại
cũ — tránh phình context vô hạn theo thời gian, đổi lại model không nhớ chính xác từng câu chữ
đã nói, chỉ nhớ các "fact" quan trọng (tình trạng da, tiền sử, thuốc đã dùng/khuyến nghị, dị
ứng...).

## 2. Luồng dữ liệu

```
Turn mới đến (worker.py::_handle_turn)
        │
        ▼
_load_memory_context(conversation_id, query_text=tin nhắn user)
        │  1. Đọc Postgres: Conversation.user_id (READ — không phạm nguyên tắc
        │     "Core là writer duy nhất", nguyên tắc đó chỉ áp dụng cho WRITE)
        │  2. memory.retrieve_context(user_id, query_text)
        │       → embed query_text (Google gemini-embedding-001, 768 chiều)
        │       → Qdrant semantic search, filter user_id, score_threshold=0.5
        ▼
SystemMessage(memory_context) được thêm vào ĐẦU state["messages"], trước HumanMessage
        │
        ▼
   ... graph chạy turn như bình thường (pre_step/reasoning/tool_wait/finalize) ...
        │
        ▼
Turn xong (status="done", KHÔNG áp dụng cho turn tạm dừng chờ ask_user)
        │
        ▼
memory.distill_and_store(user_id, conversation_id, message_id, user_content, reasoning, answer)
        │  1. Gọi LLM (get_llm(), không tools) tóm tắt toàn bộ Reasoning của turn
        │     (câu hỏi/trả lời ask_user, kết quả tool, câu trả lời cuối) thành
        │     tối đa 5 gạch đầu dòng. Rỗng (không có gì đáng nhớ) → bỏ qua, không lưu.
        │  2. embed(summary) → upsert vào Qdrant (payload: user_id, conversation_id,
        │     message_id, summary, created_at)
        ▼
   Memory sẵn sàng cho turn kế tiếp (hội thoại này hoặc hội thoại khác của user)
```

## 3. Vì sao Qdrant (không phải bảng Postgres)

Codebase dùng SQLAlchemy model + repository cho mọi thứ khác (`Message`/`Conversation`/`User`),
nhưng memory cần **semantic search** (tìm theo độ liên quan ngữ nghĩa, không phải theo khoá
chính xác hay thời gian) — Postgres thuần không hỗ trợ việc này tốt (cần extension `pgvector`
mới làm được). Qdrant là kho dữ liệu **hoàn toàn tách biệt** khỏi Postgres:

- Nguyên tắc "Core là writer duy nhất của bảng `messages`" (từ `agent_response_queue`,
  `docs/async-api-doc.md` mục 6) **chỉ áp dụng cho Postgres** — Qdrant không nằm trong phạm vi
  đó. Agent Worker đọc/ghi Qdrant **trực tiếp**, không qua RabbitMQ/Core.
- Không dùng LangGraph Store API (`langgraph.store.*`) dù đã có sẵn trong dependency — giữ 1
  pattern nhất quán (client wrapper module-level, cùng phong cách `redis_client.py`/
  `rabbitmq_client.py`) thay vì thêm 1 khái niệm mới vào codebase.

## 4. File liên quan

| File | Vai trò |
|---|---|
| `app/infra/qdrant_client.py` | Client wrapper thuần: `ensure_collection`/`upsert_memory`/`search_memories`. Dùng `query_points()` (không phải `.search()` — đã deprecate ở `qdrant-client>=1.10`). |
| `app/agent/memory.py` | Business logic: `distill_and_store()`, `retrieve_context()`, `_reasoning_transcript()`. |
| `app/agent/worker.py` | Nối vào luồng turn: `_load_memory_context()` (gọi trong `_initial_state()`), lệnh gọi `distill_and_store()` sau khi turn `status="done"`, `main()` gọi `ensure_collection()` lúc khởi động. |

## 5. Model embedding

`models/gemini-embedding-001` (Google, cùng provider với `AGENT_MODEL`, dùng chung
`GOOGLE_API_KEY` — không cần thêm provider mới). Mặc định trả vector 3072 chiều nhưng hỗ trợ
Matryoshka truncation qua tham số `output_dimensionality` — dự án giới hạn về **768** chiều
(`app/agent/memory.py::_EMBEDDING_DIM`, PHẢI khớp `app/infra/qdrant_client.py::EMBEDDING_DIM`)
để vector gọn hơn, đủ tốt cho tập dữ liệu memory nhỏ.

**Lưu ý lịch sử**: model cũ `models/text-embedding-004` (nhắc tới trong 1 số hướng dẫn cũ) đã
bị Google khai tử cho API key mới (404 NOT_FOUND) — xác nhận qua `ListModels`
(`supportedGenerationMethods` chứa `embedContent`) trước khi chọn model, đừng giả định tên
model còn hoạt động.

## 6. Chịu lỗi

Toàn bộ `memory.py` (`distill_and_store`, `retrieve_context`) tự bắt exception, chỉ `print` log
— KHÔNG bao giờ raise ra ngoài. Qdrant down / LLM distill lỗi / embedding lỗi đều không được
làm hỏng turn chính (đã kiểm chứng: tắt hẳn container `derma-qdrant` giữa chừng, turn vẫn hoàn
tất bình thường, chỉ thiếu phần memory).

## 7. Giới hạn đã biết

- `retrieve_context`/`distill_and_store` không dùng transaction/queue nào đảm bảo — nếu Worker
  crash giữa lúc distill, memory của turn đó bị mất (chấp nhận được vì memory là phụ trợ).
- Không có cơ chế dọn memory cũ/trùng lặp — theo thời gian số point trong Qdrant tăng vô hạn.
- `score_threshold=0.5` (cosine) là giá trị chọn tạm — chưa tuning theo dữ liệu thật.
