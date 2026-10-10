# [Pending] Làm giàu Knowledge Base cùng chatbot

Requirement M9.4 (xem [requirements.md](../overview/requirements.md)): bác sĩ phối hợp với chatbot để tra cứu và làm
giàu KB. Chưa làm, chưa có entity trong `dto/base`. Tài liệu này ghi lại ý tưởng để chốt luồng trước khi làm.

## 1. Vấn đề

KB hiện chỉ được bổ sung theo 2 cách, đều là nạp nguyên lô:
- Script nạp guideline / KG (`core/data_ingest/`).
- Pipeline số hoá sách (`/doctor/documents`).

Chưa có cách bổ sung **từng mẩu tri thức nhỏ** phát hiện trong lúc dùng hệ thống, ví dụ:
- Chatbot không tìm được guideline cho một bệnh, phải dùng web.
- Bác sĩ thấy câu trả lời thiếu ý hoặc lỗi thời.
- Một ca bệnh tham khảo (`medical_records.is_reference_case`) cần được tóm tắt thành tri thức tra cứu được.

## 2. Luồng đề xuất

```
Nguồn đề xuất                      Duyệt                      Nạp
─────────────                      ─────                      ───
Chatbot (khi phải dùng web /  ─┐
  KB không trả lời được)       ├─▶ KnowledgeSuggestion ─▶ bác sĩ duyệt / sửa ─▶ nạp Qdrant (collection guideline
Bác sĩ (từ một câu trả lời    ─┤     status = pending        status = approved      hoặc collection riêng)
  hoặc tự nhập)                │                          ─▶ từ chối: rejected
Ca bệnh tham khảo             ─┘
```

1. **Tạo đề xuất**:
   - Chatbot gọi một tool (ví dụ `suggest_knowledge`) khi phải dựa vào web hoặc KB không có thông tin.
   - Bác sĩ bấm "đề xuất bổ sung" trên một câu trả lời, hoặc tự nhập.
2. **Duyệt**: bác sĩ xem danh sách đề xuất `pending`, sửa nội dung, rồi duyệt hoặc từ chối. Chỉ nội dung đã duyệt mới
   vào KB, vì tri thức y khoa sai sẽ lan sang mọi câu trả lời sau.
3. **Nạp**: embedding + upsert Qdrant, payload ghi rõ nguồn là "đề xuất đã duyệt" và người duyệt, để chatbot trích dẫn
   và có thể gỡ khi cần.

## 3. Entity đề xuất (cần duyệt trước khi thêm vào `dto/base`)

```python
class KnowledgeSuggestion(BaseModel):
    id: str
    title: str                      # bệnh / chủ đề
    content: str                    # nội dung tri thức đề xuất
    sources: list[Source] = []      # căn cứ (web, guideline, sách...) — dùng lại `Source` của `dto/common/chat.py`
    origin: Literal["chatbot", "doctor", "reference_case"]
    origin_message: Message | None = None        # câu trả lời / tin nhắn sinh ra đề xuất
    origin_record: MedicalRecord | None = None   # ca bệnh tham khảo, nếu có
    proposed_by: User | None = None              # None khi chatbot tự đề xuất
    status: Literal["pending", "approved", "rejected"] = "pending"
    reviewed_by: Doctor | None = None
    review_note: str = ""
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
```

Bảng `knowledge_suggestions` tương ứng: FK `origin_message_id` → `messages`, `origin_record_id` → `medical_records`,
`proposed_by_id` → `users`, `reviewed_by_id` → `doctors` (đều `SET NULL`); `sources` để JSONB.

## 4. Câu hỏi cần chốt

- Tri thức đã duyệt nạp chung collection chunk sách (`derma_document_chunks`) hay collection riêng?
- Chatbot có được tự tạo đề xuất không, hay chỉ bác sĩ? Nếu có, cần giới hạn để tránh rác (ví dụ chỉ khi phải dùng web).
- Ca bệnh tham khảo tự sinh đề xuất khi bác sĩ đánh dấu, hay bác sĩ chủ động tạo?
- Ẩn thông tin định danh của ca bệnh ở bước nào (khi tạo đề xuất hay khi nạp)?

## 5. Phụ thuộc

- M1 (đăng nhập + vai trò) để biết ai đề xuất / ai duyệt.
- M9.3 (chatbot tra được tài liệu đã nạp) nên làm trước, để đo được KB đang thiếu gì.
