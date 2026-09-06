# API Doc — REST (Core)

Đặc tả REST API của Core (`/api/v1`), theo đúng hợp đồng đã thống nhất với Frontend
(`fe/docs/backend-contract.md`, nguồn chuẩn kiểu dữ liệu: `fe/features/chat/types.ts`).
Xem [`async-api-doc.md`](./async-api-doc.md) cho luồng SSE (`GET .../stream`), và
[`db-diagram.md`](./db-diagram.md) cho schema DB đứng sau các endpoint này.

Đặc tả máy đọc được (OpenAPI 3.1): [`openapi.yaml`](./openapi.yaml) — **sinh tự động** từ
chính FastAPI app (`main.app.openapi()`), không viết tay. Regenerate sau khi đổi route/DTO:

```bash
cd core && python scripts/gen_openapi.py
```

> ✅ **Đã implement** — `app/api/conversation_api.py`. Sai khác nhỏ so với đặc tả gốc:
> `POST /conversations` publish turn đầu qua `MessageService.start_new_turn` (dùng chung logic
> với nhánh "turn mới" của `send_message`); `answer_question` trả `404` (không phải mã lỗi có
> cấu trúc `{"error": {...}}` như mục 0 đề xuất — global exception handler chuẩn hoá lỗi
> **chưa làm**, dùng `HTTPException` mặc định của FastAPI tạm thời).

## 0. Quy ước chung

- **Base path**: `/api/v1` (`settings.API_V1_PREFIX`).
- **Envelope**: mọi response 200/201 bọc qua `ApiResponse[T]` / `PageResponse[T]`
  (`app/dto/common.py`) — `{"data": ...}`. Lỗi trả `{"error": {"code": str, "message": str}}`
  (đề xuất — **chưa có** global exception handler áp dụng chuẩn này, cần làm khi triển khai).
- **camelCase trên wire, snake_case trong Python**: Frontend dùng camelCase
  (`conversationId`, `createdAt`, `clientMessageId`...). DTO Python vẫn đặt field
  `snake_case` theo quy ước (`quy-uoc.md` mục 8), nhưng cấu hình
  `alias_generator=to_camel, populate_by_name=True` (Pydantic v2) để serialize/parse đúng
  camelCase ra ngoài. Áp dụng cho **mọi** DTO request/response ở đây, không chỉ riêng lẻ.
- **Auth**: **chưa có** ở giai đoạn hiện tại. `userId` truyền tay từ client (giống
  `CreateConversationInput.userId` trong contract FE) — cần thay bằng session/JWT khi có hệ
  thống auth thật; đến lúc đó mọi endpoint bên dưới cần thêm 1 bước resolve user từ token
  thay vì đọc `userId` từ query/body.

## 1. Conversation

### 1.1 `GET /conversations`

Liệt kê hội thoại của 1 user.

| | |
|---|---|
| Query | `userId: str` (bắt buộc, tạm thời — xem ghi chú Auth ở mục 0) |
| Response | `200` `ApiResponse[list[ConversationOutput]]` |

```json
{ "data": [ { "id": "conv-1", "title": "Chăm sóc da mụn trứng cá", "createdAt": "2026-08-19T09:00:00Z", "updatedAt": "2026-08-19T09:05:00Z" } ] }
```

### 1.2 `POST /conversations`

Tạo hội thoại mới, **kèm tin nhắn đầu tiên nếu `initMessage` không rỗng**.

| | |
|---|---|
| Body | `CreateConversationInput { userId: str, initMessage: str, title?: str }` |
| Response | `201` `ApiResponse[ConversationOutput]` |

**Quyết định thiết kế** (contract FE không nói rõ, Core chọn để FE chỉ cần 1 request):
1. Tạo row `conversations` (`title` = `title` truyền vào hoặc `""`).
2. **Chỉ khi `initMessage.strip()` khác rỗng**: lưu thành `messages` row đầu tiên
   (`role="user"`, `status="done"`) + publish turn đầu tiên vào `agent_request_queue`
   (giống hệt gọi `POST .../messages` ngay sau khi tạo) — FE chỉ cần mở
   `GET /conversations/{id}/stream` ngay sau khi nhận response 201 là thấy assistant
   trả lời.
3. `initMessage` rỗng (FE hiện tại — `store.ts` luôn tạo conversation với
   `initMessage=""` rồi gọi `POST .../messages` riêng cho tin đầu tiên, tránh trùng
   lặp) → **không** mở turn nào — mở turn với content rỗng vừa vô nghĩa vừa bị LLM từ
   chối request, để lại Redis "active_turn" key treo vĩnh viễn.

### 1.3 `GET /conversations/{conversationId}/messages`

| | |
|---|---|
| Path | `conversationId: str` |
| Response | `200` `ApiResponse[list[MessageOutput]]`, sắp xếp `createdAt` tăng dần |

`MessageOutput` — xem mục 3 (bao gồm cả `metadata` optional theo loại, xem `db-diagram.md`
mục 2 cho quy ước tổ chức).

## 2. Message

### 2.1 `POST /conversations/{conversationId}/messages`

Gửi 1 tin nhắn user **mới** — có thể là **tin nhắn mở đầu 1 turn mới**, hoặc **Steer** (tin
nhắn gửi thêm khi turn trước đó của conversation còn đang chạy — xem `async-api-doc.md` mục 5
cho khái niệm Steer, định nghĩa gốc ở `fe/docs/backend-contract.md` mục 5).

> Endpoint này **KHÔNG** dùng để trả lời câu hỏi agent đang chờ (`tool_ask`/`choice`) — trả
> lời câu hỏi đi qua endpoint riêng (mục 2.2), vì đó là kết quả của 1 tool call đang treo,
> không phải 1 tin nhắn mới của user. Xem lý do ở `async-api-doc.md` mục 4.

| | |
|---|---|
| Path | `conversationId: str` |
| Body | `SendMessageInput` |
| Response | `202 Accepted` `ApiResponse[MessageOutput]` — **user message vừa lưu**, chưa có assistant message (lấy qua SSE) |

```python
class SendMessageInput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    client_message_id: str          # id tạm do FE sinh, dùng để ghép luồng SSE
    content: str
    model_id: str | None = None      # "derma-ai-pro" / "derma-ai-lite"
    attachments: list[FileAttachmentDto] | None = None
    selection: MessageSelectionRefDto | list[MessageSelectionRefDto] | None = None
```

**Xử lý trong route** (tóm tắt, chi tiết xem `async-api-doc.md` mục 5):
1. Kiểm tra turn hiện tại của `conversationId` có đang chạy không (chưa `message.done`, và
   không đang tạm dừng chờ `tool_ask` — trường hợp đó route này phải từ chối, xem mục 2.2):
   - **Không đang chạy** → lưu `messages` row (`role="user"`, `status="done"`), publish
     `AgentTurnRequest` bình thường, tạo turn mới.
   - **Đang chạy** (Steer) → lưu `messages` row (`role="user"`, `status="pending"`), publish
     request kèm cờ `is_steer=true` vào `agent_request_queue`. `status` sẽ được Agent Worker
     cập nhật thành `"queued"` khi `pre_step` thực sự đưa vào context (không phải ở route này
     — xem `async-api-doc.md` mục 5–6).
2. Trả `202` với `MessageOutput` của user message vừa lưu — **không đợi** agent xử lý xong.

### 2.2 `POST /conversations/{conversationId}/questions/{questionId}/answer`

Trả lời 1 câu hỏi agent đang chờ (`tool_ask`, xem `async-api-doc.md` mục 3–4) —
**không** tạo `messages` row mới, **không** phải Steer.

| | |
|---|---|
| Path | `conversationId: str`, `questionId: str` |
| Body | `MessageAnswerDto { optionId: str, label: str, custom?: bool }` |
| Response | `202 Accepted` (không body, hoặc `ApiResponse[MessageOutput]` của assistant message đang `status="question"` vừa cập nhật `choice.answered`) |

**Xử lý trong route** (chi tiết xem `async-api-doc.md` mục 4):
1. Tìm assistant `messages` row đang `status="question"` chứa reasoning step có
   `choice.questionId == questionId`; `404` nếu không có (đã trả lời rồi, hoặc sai id).
2. Publish "resume request" vào `agent_request_queue` (không phải `AgentTurnRequest` mới) kèm
   `conversation_id` + `questionId`.
3. Trả `202` ngay — Agent Worker resume (LangGraph `Command(resume=...)`) và publish tiếp qua
   Redis; client tự mở lại SSE (`GET .../stream`) để nhận phần còn lại của turn.

## 3. `ConversationOutput` / `MessageOutput`

```python
class ConversationOutput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOutput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "queued", "streaming", "done", "question"]
    metadata: MessageMetadataDto | None = None   # xem db-diagram.md mục 2
    created_at: datetime
```

`MessageMetadataDto` gom toàn bộ field optional-theo-loại (`reasoning`, `selectionRef`,
`attachments`, `choice`, `sources`, `isOptionResponse`) — quy ước đầy đủ + lý do gộp vào 1 DTO
thay vì field rời từng cái nằm ở `db-diagram.md` mục 2.

> ⚠️ `"pending"` **chưa có** trong `MessageStatus` phía FE (`fe/features/chat/types.ts` hiện
> chỉ có `"streaming" | "done" | "queued" | "question"`) — đây là status mới, sinh ra từ luồng
> Steer (`async-api-doc.md` mục 5). Cần đồng bộ với FE (thêm `"pending"` vào `MessageStatus`)
> trước khi Core thực sự trả giá trị này ra API.
