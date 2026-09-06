  # Data Contract — Backend ↔ Frontend (Chat)

Phiên bản: `1.5` · Ngày: 2026-08-24
Trạng thái: **giả định** — dựa trên giao diện frontend hiện tại (`fe/features/chat/types.ts`). Backend có thể giữ nguyên các trường dưới đây; nếu khác, chỉ cần chỉnh tầng `services/chat.sse.ts`.

---

## 1. Tổng quan

| Khu vực | Phương thức | Mô tả |
|---|---|---|
| Lịch sử (hội thoại, tin nhắn) | REST (JSON) | Liệt kê hội thoại, chi tiết tin nhắn (bao gồm các nguồn tham chiếu `sources`) |
| Gửi tin nhắn + nhận phản hồi | `POST` trả về `text/event-stream` | Stream reasoning, câu hỏi, nguồn tham khảo, nội dung |

### Biến môi trường

| Biến | Bắt buộc | Giá trị mặc định | Mô tả |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | khi dùng BE thật | `/api/v1` | Base URL REST + SSE |
| `NEXT_PUBLIC_USE_MOCK` | không | `true` | `false` = dùng BE thật (POST + SSE) |
| `NEXT_PUBLIC_ONLYOFFICE_DOCS_URL` | chỉnh sửa canvas | `http://localhost:8080` | URL OnlyOffice Document Server (browser truy cập) |
| `NEXT_PUBLIC_APP_URL` | chỉnh sửa canvas | `http://localhost:3000` | URL công khai của app để **Document Server** tải văn bản + gửi callback (không được là `localhost` khi Document Server chạy trong container) |
| `ONLYOFFICE_JWT_SECRET` | khi Document Server bật JWT | trống | Bí mật ký token JWT (HS256) cho config/callback OnlyOffice |

---

## 2. REST — Lịch sử

### 2.1 Liệt kê hội thoại

`GET {API_BASE}/conversations`

```json
// 200 OK
{
  "data": [
    {
      "id": "conv-1",
      "title": "Chăm sóc da mụn trứng cá",
      "createdAt": "2026-08-19T09:00:00.000Z",
      "updatedAt": "2026-08-19T09:05:00.000Z"
    }
  ]
}
```

### 2.2 Tạo hội thoại

`POST {API_BASE}/conversations`

```json
// Request (CreateConversationInput)
{
  "userId": "user-1",
  "initMessage": "Tư vấn chăm sóc da mụn trứng cá",
  "title": "Chăm sóc da mụn trứng cá"
}

// 201 Created
{ "data": { "id": "conv-9", "title": "Chăm sóc da mụn trứng cá", "createdAt": "…", "updatedAt": "…" } }
```

> Frontend gửi `CreateConversationInput` gồm `userId`, `initMessage`, và `title` khi tạo cuộc trò chuyện mới.

### 2.3 Lấy tin nhắn của hội thoại

`GET {API_BASE}/conversations/{conversationId}/messages`

```json
// 200 OK
{ "data": [ <ChatMessage>, ... ] }
```

Trả về mảng `ChatMessage` (xem mục 4), sắp xếp theo `createdAt` tăng dần.

---

## 3. Gửi tin nhắn & stream phản hồi

### 3.1 Request

`POST {API_BASE}/conversations/{conversationId}/messages`

```json
{
  "corrId": "uuid-do-client-sinh",
  "content": "Tư vấn điều trị nám má",
  "modelId": "derma-ai-pro",
  "metadata": {
    "corr_id": "uuid-do-client-sinh",
    "selection_ref": [
      { "message_id": "m1", "text": "đoạn bôi đen" }
    ],
    "attachments": [
      { "id": "f1", "name": "hop-dong.pdf", "size": 102400, "type": "application/pdf" }
    ]
  }
}
```

### 3.2 Stream phản hồi

`GET {API_BASE}/conversations/{conversationId}/stream` (Content-Type: `text/event-stream`)

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `clientMessageId` | string (UUID) | ✅ | Id **tạm** do client sinh để ghép luồng; server echo lại trong event `message.started` |
| `content` | string | ✅ | Nội dung tin nhắn |
| `modelId` | string | ❌ | Mô hình xử lý (`derma-ai-pro` / `derma-ai-lite`) |
| `attachments` | `FileAttachment[]` | ❌ | Chỉ metadata tệp đính kèm (nội dung file tải riêng) |
| `selection` | `MessageSelectionRef \| null` | ❌ | Có mặt khi người dùng **bôi đen một đoạn tin nhắn** và hỏi về đoạn đó |
| `answer` | `MessageAnswer \| null` | ❌ | Có mặt khi đây là câu trả lời cho câu hỏi agent (mục 3.4) |

> **UUID thật của message do SERVER sinh.** Server tạo `messageId`, gửi event đầu tiên `message.started` để client biết; các event sau đều mang `messageId` này.

### 3.1a Hỏi về đoạn tin nhắn được bôi đen

Người dùng bôi đen một hoặc nhiều đoạn trong tin nhắn (user hoặc assistant) rồi đặt câu hỏi. Client gửi `selection` (có thể là 1 đối tượng hoặc mảng các đối tượng):

```json
{
  "clientMessageId": "uuid-moi-do-client-sinh",
  "content": "Điều này áp dụng cho trường hợp của em không?",
  "selection": [
    {
      "messageId": "msg-server-sinh-1",
      "text": "Retinoid bôi buổi tối, khởi đầu cách ngày để da làm quen"
    },
    {
      "messageId": "msg-server-sinh-2",
      "text": "Benzoyl peroxide giúp giảm đề kháng kháng sinh khi trị mụn"
    }
  ]
}
```

| `selection` | Kiểu | Mô tả |
|---|---|---|
| `MessageSelectionRef \| MessageSelectionRef[]` | object hoặc array | 1 hoặc danh sách các đoạn trích bôi đen kèm `messageId` và `text` |

> Backend lưu `selectionRef` vào tin user tương ứng (`ChatMessage.selectionRef` dạng dict hoặc list) để lịch sử hiển thị đúng danh sách các đoạn trích khi reload.

### 3.2 Response — định dạng SSE

- `Content-Type: text/event-stream`
- Mỗi event là một khối `data: <json>` kết thúc bằng dòng trống:

```
data: {"type":"message.started","clientMessageId":"uuid-client-gui","conversationId":"conv-1","messageId":"msg-server-sinh"}

data: {"type":"reasoning.step_started","messageId":"msg-server-sinh","conversationId":"conv-1","stepId":"msg-server-sinh-step-1","title":"Nhận diện vấn đề"}

data: {"type":"reasoning.step_delta","messageId":"msg-server-sinh","conversationId":"conv-1","stepId":"msg-server-sinh-step-1","delta":"Phân tích"}

data: {"type":"reasoning.step_completed","messageId":"msg-server-sinh","conversationId":"conv-1","stepId":"msg-server-sinh-step-1"}

data: {"type":"question","messageId":"msg-server-sinh","conversationId":"conv-1","questionId":"msg-server-sinh-q1","text":"Bạn muốn tìm hiểu khía cạnh nào?","options":[{"id":"qk1","label":"Chọn thuốc bôi theo mức độ mụn"}]}

data: {"type":"message.delta","messageId":"msg-server-sinh","conversationId":"conv-1","delta":"Theo Hướng dẫn điều trị mụn trứng cá"}

data: {"type":"message.done","messageId":"msg-server-sinh","conversationId":"conv-1","reasoning":[…]}
```

- Cuối stream có thể gửi `data: [DONE]` (client bỏ qua).
- Server phải đóng connection sau khi gửi `message.done` **hoặc** `question`.

### 3.3 Event types (Server → Client push)

| `type` | Khi nào | Payload bổ sung | Ý nghĩa |
|---|---|---|---|
| `message.started` | **event đầu tiên** | `clientMessageId` (echo), `messageId` (server sinh) | Báo uuid thật của message |
| `reasoning.step_started` | đầu mỗi bước | `messageId`, `stepId`, `title` | Bắt đầu bước suy luận (spinner + tiêu đề) |
| `reasoning.step_delta` | lặp nhiều lần | `messageId`, `stepId`, `delta` | Stream token của bước |
| `reasoning.step_completed` | cuối bước | `messageId`, `stepId` | Bước hoàn tất (✓) |
| `question` | agent cần người dùng chọn | `messageId`, `questionId`, `text`, `options[]` | Dừng luồng, chờ lựa chọn |
| `message.delta` | lặp nhiều lần | `messageId`, `delta` | Stream nội dung cuối |
| `message.done` | hoàn tất | `messageId`, `reasoning?` (toàn bộ bước), `sources?` (danh sách tài liệu y khoa tham chiếu) | Kết thúc luồng bình thường |
| `document.started` | trước khi soạn văn bản | `messageId`, `documentId`, `title` | Bắt đầu stream văn bản soạn sẵn (canvas) |
| `document.delta` | lặp nhiều lần | `messageId`, `documentId`, `delta` | Stream token nội dung HTML của văn bản |
| `document.done` | soạn xong | `messageId`, `documentId`, `document?` (toàn bộ HTML) | Hoàn tất văn bản soạn sẵn |

**Thứ tự chuẩn:**

- Luồng trả lời: `message.started` → `step_started → step_delta* → step_completed` (lặp) → `message.delta*` → [`document.started → document.delta* → document.done`] → `message.done`
- Luồng hỏi: `message.started` → `step_started → … → step_completed` → `question` (dừng)

### 3.4 Luồng hỏi — người dùng lựa chọn hoặc tự nhập

1. Server gửi event `question` với `questionId` + danh sách `options`.
2. Frontend hiển thị **các lựa chọn ngay trong khung chat**: người dùng chọn 1 option hoặc tự nhập phương án (ô nhập inline).
3. Client gửi **POST mới** tới cùng endpoint, với `answer`:

```json
{
  "clientMessageId": "uuid-moi-do-client-sinh",
  "content": "Chọn thuốc bôi theo mức độ mụn",
  "answer": {
    "questionId": "msg-server-sinh-q1",
    "optionId": "qk2",
    "label": "Chọn thuốc bôi theo mức độ mụn",
    "custom": false
  }
}
```

| `answer` | Kiểu | Mô tả |
|---|---|---|
| `questionId` | string | id của câu hỏi đang trả lời |
| `optionId` | string | id option đã chọn; **`"custom"`** nếu người dùng tự nhập |
| `label` | string | nội dung lựa chọn (hoặc chữ tự nhập) |
| `custom` | boolean | `true` khi tự nhập phương án |

4. Server trả tiếp một luồng SSE (bắt đầu bằng `message.started`, thường kết thúc bằng `message.done` với kết luận).

> Backend nên **lưu `answered`** vào câu hỏi tương ứng (`ChatMessage.choice.answered`) để lịch sử hiển thị đúng lựa chọn khi reload.

### 3.5 Văn bản soạn sẵn (canvas) — Document Service + OnlyOffice

Khi tin nhắn có `document` (xem event `document.*`), người dùng có thể mở canvas chỉnh sửa và **Lưu**. Editor dùng **OnlyOffice Document Server** (không còn Quill).

**Artifact là DOCX** — văn bản được lưu/thao tác dưới dạng `.docx`, không phải HTML:
- `Document Service` (layer trung tâm) quản lý `document_id`, `version`, `base_version`, DOCX bất biến theo version.
- HTML chỉ là **bản xem trước** để khung chat hiển thị (không phải nguồn chỉnh sửa).
- Chuyển đổi HTML↔DOCX bằng `html-to-docx` / `mammoth` ở biên (Agent sinh HTML → DOCX; OnlyOffice lưu DOCX → HTML preview).

**Luồng chỉnh sửa (frontend — giả lập Document Service bằng route `/api/editor/*`):**

1. Frontend mở editor → `POST /api/editor/session` với `{ messageId, documentId, title, content }` → Document Service mở/tạo văn bản:
   - chưa có → convert HTML → DOCX bản `v1`;
   - đã có → dùng bản DOCX mới nhất.
   Trả `config` cho `new DocsAPI.DocEditor(...)` với `document.fileType: "docx"`.
2. Document Server tải DOCX qua `GET /api/editor/download/{key}`.
3. Khi lưu (nút "Lưu" → `docEditor.save()` hoặc autosave), Document Server gửi callback `POST /api/editor/callback/{key}` (body `{ status, url, key }`, `status` 2/6/7 kèm `url` file DOCX) → Document Service **tạo version mới** (`base_version` = version cũ), convert DOCX → HTML preview, lưu vào phiên.
4. Frontend đợi `savedContent` (poll `GET /api/editor/session/{key}`), rồi gọi endpoint dưới đây để lưu vào database:

`PUT {API_BASE}/chats/messages/{messageId}/document`

```json
{
  "content": "<p>HTML xem trước sau khi chỉnh sửa...</p>",
  "isCanvas": true
}
```

| Trường | Kiểu | Mô tả |
|---|---|---|
| `content` | string | HTML **xem trước** (convert từ DOCX đã lưu) — để khung chat hiển thị |
| `isCanvas` | boolean | Đánh dấu block đã được mở/chỉnh sửa như canvas |

> Backend lưu lại `ChatMessage.document` (thay `content`, cập nhật `isCanvas`) để reload hiển thị bản đã sửa.
>
> **Mock mode**: document nằm trong localStorage nên Document Server không đọc trực tiếp được — toàn bộ việc trao đổi (tải/lưu) đi qua route `/api/editor/*` của Next.js; DOCX/version nằm ở Document Service in-memory, `content` (HTML preview) cuối cùng được lưu về store/localStorage.
>
> **Version / conflict**: `DocumentService.save` nhận `expectedBaseVersion`; nếu khác `current_version` → trả **`409 VERSION_CONFLICT`**. OnlyOffice trong cùng một phiên luôn lưu lên bản mới nhất (không đối đầu); luồng **Agent** sau này gửi `{ document_id, base_version, operation }` và sẽ nhận `409` nếu user đã sửa đồng thời → Agent có thể `rebase`/`retry`.
>
> **Ghi chú**: Document Service hiện là in-memory (mất khi restart server), dùng cho dev; khi có backend thật, chuyển phần này sang backend: DOCX/version vào **S3/MinIO**, metadata/audit vào **PostgreSQL**, và backend cấp `document.url` + `callbackUrl` trực tiếp (bỏ route bridge).

---

## 4. Kiểu dữ liệu (tham chiếu)

```ts
interface Conversation {
  id: string;
  title: string;      // "" khi chưa đặt
  createdAt: string;  // ISO 8601
  updatedAt: string;
}

interface ChatMessage {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  reasoning?: ReasoningStep[];   // chỉ tin assistant
  selectionRef?: MessageSelectionRef; // đoạn bôi đen mà tin user tham chiếu
  document?: ComposedDocument;   // văn bản soạn sẵn (canvas) — chỉ tin assistant
  attachments?: FileAttachment[];// chủ yếu tin user
  createdAt: string;
  status: "streaming" | "done" | "queued";
}

interface ComposedDocument {
  id: string;
  title: string;
  content: string;   // HTML
  isCanvas?: boolean;
}

interface ReasoningStep {
  id: string;
  title: string;
  content: string;
  status: "processing" | "done";
}

interface FileAttachment {
  id: string;
  name: string;
  size: number;   // bytes
  type: string;   // MIME
}

interface MessageSelectionRef {
  messageId: string;
  text: string;
}

interface ChoiceOption {
  id: string;
  label: string;
}

interface MessageChoice {
  questionId: string;
  question: string;
  options: ChoiceOption[];
  answered?: { optionId: string; label: string; custom?: boolean };
}

interface MessageAnswer {
  questionId: string;
  optionId: string;
  label: string;
  custom?: boolean;
}
```

---

## 5. Quy ước hệ thống & Triển khai BE (`core/quy-uoc.md`)

- **Khái niệm Lượt (Message Turn)**: 1 Message Turn = 1 lần gọi LLM và thực thi lần lượt các tool cần thiết.
- **Xử lý Steer Message**: Khi Assistant đang trong quá trình suy luận (reasoning) mà người dùng gửi thêm tin nhắn hoặc chọn phương án trả lời câu hỏi tool call (`question`), tin nhắn mới được coi là một **Steer**. Steer sẽ được xử lý trong bước (step) tiếp theo của Turn.
- **Persist Tin nhắn Steer**: Khi tới lượt xử lý steer, Server phát event (`message.steered`), đồng thời **lưu tin nhắn Steer của User vào DB và đặt ngay sau tin nhắn User ban đầu của Turn** (đảm bảo thứ tự DB: `Initial User Message` -> `Steer User Message` -> `Assistant Message`).
- **Persist Tin nhắn Assistant**: **Luôn luôn chỉ persist tin nhắn của Assistant vào DB khi đã kết thúc Turn (`message.done`)**. Trong quá trình streaming hoặc tạm dừng ở trạng thái `question`, tin nhắn Assistant được duy trì trong bộ nhớ tạm (in-memory) và stream tới FE mà chưa commit vào bảng `messages`.

---

## 6. Tệp liên quan (frontend)

| Tệp | Vai trò |
|---|---|
| `fe/features/chat/types.ts` | Nguồn chuẩn của các type/event ở trên |
| `fe/services/chat.sse.ts` | Client POST + parse SSE (đổi tên event → sửa ở đây) |
| `fe/services/endpoints.ts` | Đường dẫn REST |
| `fe/services/mock/mockChatService.ts` | Mô phỏng backend (chuẩn để BE đối chiếu hành vi) |
| `fe/lib/documents/documentService.ts` | **Document Service**: versioning, DOCX bất biến, HTML↔DOCX, conflict (base_version → 409) |
| `fe/lib/documents/editorStore.ts` | Phiên chỉnh sửa OnlyOffice (key → document/version) + ký JWT |
| `fe/app/api/editor/*` | Route bridge: session / download (DOCX) / callback (save → version mới) |
| `fe/components/onlyoffice/OnlyOfficeEditor.tsx` | Component editor (nạp api.js, mở DOCX qua OnlyOffice) |

---

## 7. Lịch sử thay đổi

| Phiên bản | Ngày | Nội dung |
|---|---|---|
| `1.0` | 2026-08-21 | Bản đầu: POST + SSE, reasoning stream, luồng hỏi/lựa chọn |
| `1.1` | 2026-08-21 | UUID message do **server sinh**; thêm event `message.started` (echo `clientMessageId`); request đổi `messageId` → `clientMessageId` |
| `1.2` | 2026-08-21 | Bổ sung `selection` (bôi đen đoạn tin nhắn để hỏi): request có `selection`, `ChatMessage.selectionRef`; ví dụ request cập nhật |
| `1.3` | 2026-08-21 | Bổ sung **văn bản soạn sẵn (canvas)**: events `document.started/delta/done`, `ComposedDocument`, `ChatMessage.document`, endpoint `PUT .../document` để lưu chỉnh sửa |
| `1.4` | 2026-08-22 | Canvas chuyển sang **OnlyOffice + Document Service**: artifact là **DOCX** (HTML chỉ là bản xem trước), versioning (`base_version`, `409 VERSION_CONFLICT`), route bridge `/api/editor/*` |
| `1.5` | 2026-08-24 | Bổ sung **nguồn tham khảo (sources)** kiểu NotebookLM: thêm kiểu `ChatSource`, trường `sources` trong `ChatMessage` và event `message.done` |
