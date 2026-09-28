# Tài Liệu Quy Ước Logic Frontend, State & Event System

> **Dự án**: Derma AI Assistant (Next.js 16 + Zustand + QuillJS)  
> **Cập nhật gần nhất**: 24/08/2026  

Tài liệu này tổng hợp toàn bộ cấu trúc logic Frontend, các quy ước State management, quy trình xử lý Event real-time (Server-Sent Events) và tương tác người dùng trong ứng dụng.

---

## 1. Kiến Trúc Tổng Quan (Architecture Overview)

Ứng dụng được xây dựng theo mô hình **Unidirectional Data Flow (Luồng dữ liệu một chiều)**:
```
[SSE Real-time Events / User Actions] 
            │
            ▼
   [Zustand Stores (Central Logic)] 
            │
            ▼
   [React Components (UI Layers)]
```

- **Framework**: Next.js 16 (App Router + Turbopack) + React 19
- **State Management**: Zustand (Global stores độc lập, phản ứng tức thì)
- **Rich Text Canvas**: QuillJS v2.0.3 (Client-side rendering)
- **Styling**: Tailwind CSS v4 (`@theme inline`, hỗ trợ mượt mà Dark/Light mode)

---

## 2. Quy Ước Các State (State Management Specification)

### 2.1. Store Chính: `useChatStore` (`features/chat/store.ts`)
Là trung tâm quản lý hội thoại, tin nhắn và trạng thái khung nhập.

| Tên State / Action | Kiểu dữ liệu | Mô tả & Quy ước |
| :--- | :--- | :--- |
| `conversations` | `Conversation[]` | Danh sách tất cả các cuộc trò chuyện. |
| `activeId` | `string \| null` | ID cuộc trò chuyện đang được chọn. `null` nghĩa là đang ở trang "Hội thoại mới". |
| `messagesByConversation` | `Record<string, ChatMessage[]>` | Lưu danh sách tin nhắn theo key là `conversationId`. |
| `activeStreams` | `Record<string, number>` | Số luồng AI đang streaming theo từng `conversationId` (cho phép gửi tin song song ở các chat khác nhau). |
| **`inputsByConversation`** | `Record<string, ConversationInputState>` | **Đồng bộ trạng thái ô nhập theo từng `conversationId`**. Lưu nháp (`value`), kỹ năng chọn (`selectedSkill`), tệp đính kèm (`files`), và trích dẫn (`pendingSelection`). |
| `selectedModelId` | `string` | Mô hình AI được chọn (ví dụ: `gemini-2.5-flash`, `gemini-2.5-pro`). |

#### Các Actions chính của `useChatStore`:
- `getInputState(convId?: string | null)`: Lấy trạng thái ô nhập hiện tại của hội thoại (nếu `convId` không truyền sẽ dùng `activeId` hoặc `"new"`).
- `setInputState(convId: string | null, patch: Partial<ConversationInputState>)`: Cập nhật trạng thái ô nhập cho hội thoại tương ứng.
- `selectConversation(id: string)`: Chuyển đổi cuộc trò chuyện active (ô nhập tự động chuyển theo `id`).
- `startNewChat()`: Chuyển sang trạng thái hội thoại mới (`activeId = null`).
- `sendMessage(content, options)`: Gửi tin nhắn, khởi tạo luồng stream AI và tự động reset `inputsByConversation` của hội thoại đó.
- `answerChoice(messageId, answer)`: Gửi phản hồi câu hỏi AI, xóa `choice` khỏi tin nhắn Assistant và tạo **1 tin nhắn User mới** được tổng hợp nội dung gồm `[Câu hỏi]` và `[Trả lời]`.

---

### 2.2. Store UI: `useUiStore` (`features/chat/uiStore.ts`)
Quản lý trạng thái hiển thị các panel bên phải và các tương tác điều hướng UI.

| State / Action | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `editing` | `{ messageId, documentId } \| null` | Quản lý trạng thái mở Panel trình chỉnh sửa văn bản **Quill Editor**. |
| `activeSource` | `SourceRef \| null` | Quản lý trạng thái mở Panel xem tài liệu y khoa tham khảo. |
| `highlightedMessageId` | `string \| null` | ID tin nhắn đang được highlight (tự động nháy viền trong 2 giây). |

---

### 2.3. Store Trích Dẫn: `useSelectionStore` (`features/chat/selectionStore.ts`)
- `pending`: `MessageSelectionRef | null` — Đoạn văn bản bôi đen từ tin nhắn hoặc Quill Editor đang chờ người dùng đặt câu hỏi trong `ChatInput`.

---

## 3. Quy Ước Các Event Lắng Nghe (Event System)

### 3.1. Server-Sent Events (SSE Stream Events from Backend)
Hệ thống lắng nghe sự kiện real-time thông qua `chatService.onEvent(handleEvent)`:

```typescript
type ChatStreamEvent =
  | { type: "message.started"; clientMessageId: string; messageId: string }
  | { type: "message.delta"; messageId: string; delta: string }
  | { type: "message.done"; messageId: string; reasoning?: ReasoningStep[] }
  | { type: "reasoning.step_started"; messageId: string; stepId: string; title: string }
  | { type: "reasoning.step_delta"; messageId: string; stepId: string; delta: string }
  | { type: "reasoning.step_completed"; messageId: string; stepId: string }
  | { type: "question"; messageId: string; questionId: string; text: string; options: ChoiceOption[]; conversationId: string }
  | { type: "document.started"; messageId: string; documentId: string; title: string }
  | { type: "document.delta"; messageId: string; delta: string }
  | { type: "document.done"; messageId: string; document?: ComposedDocument };
```

#### Quy trình xử lý chi tiết theo Event Type:
1. **`message.started`**: Thay thế ID tạm ở client (`clientMessageId`) bằng ID chính thức của Server (`messageId`).
2. **`message.delta`**: Nạp từng token phản hồi của AI vào `content` của tin nhắn.
3. **`message.done`**: Đánh dấu tin nhắn hoàn thành (`status: "done"`), giảm số lượng active stream.
4. **`reasoning.step_started / delta / completed`**: Cập nhật từng bước suy luận (`ReasoningStep`). Khối này mặc định thu gọn (`open: false`) và hiển thị dạng **Vertical Icon Timeline**.
5. **`question`**: Kích hoạt trạng thái câu hỏi -> tự động mở **`QuestionModal`** nổi ngay trên thanh gõ `ChatInput`.
6. **`document.started / delta / done`**: Tạo khối văn bản **Document Block** dạng xem trước (Preview Card) trong tin nhắn. Nhấp vào thẻ sẽ mở **Quill Editor**.

---

### 3.2. Sự Kiện Tương Tác Người Dùng (DOM & User Events)

#### A. Sự Kiện Bôi Đen Văn Bản trong Quill Editor (`QuillEditor.tsx`)
- **Event**: `quill.on("selection-change", (range) => ...)`
- **Logic**:
  - Khi `range.length > 0`, lấy tọa độ `selection.bounds.bottom` bên dưới dòng bôi đen.
  - Hiển thị Toolbar nổi với màu đặc 100% (`opacity-100 bg-popover`):
    - **Nút "Sửa bằng AI"**: Mở ô nhập prompt để AI thay thế/sửa trực tiếp đoạn văn bản bôi đen trong Quill Canvas.
    - **Nút "Hỏi về đoạn này"**: Đẩy trích dẫn xuống `ChatInput` (`pendingSelection`) để người dùng hỏi AI trong khung chat chính.

#### B. Sự Kiện Tự Đóng Khi Mất Focus (Click Outside)
- **Event**: `window.document.addEventListener("mousedown", handleClickOutside)`
- **Áp dụng**:
  - **`QuestionModal.tsx`**: Nếu nhấp chuột ra ngoài Popup câu hỏi, Popup sẽ tự động thu gọn thành nút chip thông báo (`⚡ Có câu hỏi từ AI (Nhấn để trả lời)`).
  - **`QuillEditor.tsx`**: Nếu nhấp chuột ra ngoài Popup sửa AI, Toolbar sửa sẽ tự động đóng.

#### C. Điều Hướng Bàn Phím (`Keyboard Nav`)
- **Phím `ArrowLeft` (←) / `ArrowRight` (→)**: Điều hướng giữa các câu hỏi trong `QuestionModal` khi có danh sách câu hỏi.
- **Phím `/` (Slash Command)**: Mở menu chọn kỹ năng (Skill Menu) ngay tại ô gõ chat `ChatInput`.

---

## 4. Sơ Đồ Luồng Xử Lý (Data Flow Sequences)

### 4.1. Luồng Hỏi/Đáp Qua Popup (`Question Event Flow`)
```
AI Server Event: "question"
           │
           ▼
patchMessage(status: "question")
           │
           ▼
[QuestionModal] tự nổi lên trên ChatInput
           │
 ┌─────────┴────────────────────────┐
 │ Người dùng chọn/nhập phương án   │
 └─────────┬────────────────────────┘
           ▼
answerChoice() được gọi:
 ├── Xóa `choice` khỏi tin nhắn Assistant (không dính vết form câu hỏi)
 ├── Tạo 1 tin nhắn User mới chứa:
 │     "[Câu hỏi] ... \n [Trả lời] ..."
 └── Gửi tin nhắn đến AI Server để tiếp tục luồng trả lời
```

### 4.2. Luồng Bôi Đen & Sửa Văn Bản Trên Quill Editor
```
Người dùng bôi đen văn bản trong Quill Canvas
           │
           ▼
Lắng nghe `selection-change` -> Tính `bounds.bottom`
           │
           ▼
Hiển thị Toolbar nổi BÊN DƯỚI dòng bôi đen (không che chữ)
 ├── Chọn "Hỏi về đoạn này"  ──> Đẩy trích dẫn xuống `ChatInput`
 └── Chọn "Sửa bằng AI"     ──> Nhập prompt -> AI gọi API -> Quill replaceText
```

---

## 5. Quy Chuẩn Đặt Tên & Cấu Trúc File (Code Conventions)

1. **State Store**: Đặt trong `features/chat/store.ts` (Global Chat State) và `uiStore.ts` (UI State).
2. **Components**:
   - `MessageBubble.tsx`: Hiển thị tin nhắn User (bong bóng bên phải) và Bot (Markdown thuần bên trái, không đóng khung bubble).
   - `DocumentBlock.tsx`: Thẻ preview gọn gàng cho văn bản soạn sẵn trong tin nhắn.
   - `ReasoningSection.tsx`: Timeline các bước suy luận dạng icon dọc nối liền.
   - `QuestionModal.tsx`: Popup câu hỏi nổi trên ô chat, tự thu gọn khi click ra ngoài.
   - `QuillEditor.tsx`: Trình soạn thảo văn bản giàu tính năng với AI prompt bôi đen.

---
*Tài liệu này là chuẩn quy ước chính thức cho hệ thống logic Frontend của Derma AI.*
