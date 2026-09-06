# Async API Doc — SSE (Core)

Đặc tả luồng **Server-Sent Events** mà Core phát ra cho Frontend trong lúc Agent Worker xử
lý 1 turn. Nguồn chuẩn kiểu event: `fe/features/chat/types.ts` (`FlatStreamEvent`) — tài liệu
này bám theo đó, không theo mô tả cũ hơn (event `question` độc lập) trong
`fe/docs/backend-contract.md` mục 3.3 (xem ghi chú mục 3). Xem
[`../../docs/kien-truc-he-thong.md`](../../docs/kien-truc-he-thong.md) mục 3 cho cách Core
nhận các event này từ Redis Pub/Sub (Agent Worker là nguồn phát thật sự — Core chỉ forward),
và [`../app/kien-truc-agent.md`](../app/kien-truc-agent.md) cho cơ chế pause/resume phía Agent
(tool `ask_user`, `interrupt()`/checkpointer).

Đặc tả máy đọc được (AsyncAPI 2.6.0): [`asyncapi.yaml`](./asyncapi.yaml) — **viết tay**
(khác `openapi.yaml`, không có auto-generate từ SSE) — tự đồng bộ lại khi đổi event contract
trong `app/agent/worker.py`.

> ✅ **Đã implement** — `app/agent/worker.py`, ĐÚNG theo đặc tả gốc (mục 6): assistant message
> được relay qua `agent_response_queue` để **Core** persist (`app/agent/response_consumer.py`,
> đăng ký lúc khởi động trong `core/main.py`'s lifespan) — Worker (và `pre_step` trong
> `app/agent/graph.py`) chỉ publish `AgentResponseMessage` (`app/agent/schemas.py`), không đụng
> Postgres. Steer (mục 5) cũng không kích hoạt `astream()` riêng — worker chỉ no-op khi nhận
> `is_steer=true`; việc "nạp" Steer do chính `pre_step` của turn đang chạy tự đọc DB
> (`MessageRepository.list_pending_steers` — vẫn đọc trực tiếp, chỉ phần GHI status đi qua
> queue). Reasoning "gọi LLM" stream **token thật** từ `llm.astream()` qua
> `langgraph.config.get_stream_writer()` (`stream_mode=["values","custom"]` ở
> `_drive_graph()`), không còn giả lập chunk cố định sau khi model trả lời xong. Giới hạn đã
> biết: nếu turn gốc kết thúc đúng lúc Steer vừa tới, Steer sẽ bị bỏ lỡ — chưa xử lý race này
> ở bản hiện tại.

## 1. Endpoint

`GET /api/v1/conversations/{conversationId}/stream`

- `Content-Type: text/event-stream`.
- Core: `psubscribe`/`subscribe` kênh Redis `agent:events:{conversationId}`
  (`app/core/constants.py:AGENT_EVENTS_CHANNEL`), forward **nguyên văn** từng message nhận
  được ra client dạng `data: <json>\n\n` — không transform, không buffer chờ đủ turn.
- Đóng connection khi nhận sentinel `STREAM_DONE_SENTINEL` (`[DONE]`) trên kênh Redis, tương
  ứng lúc Agent Worker publish xong `message.done` **hoặc** turn tạm dừng chờ trả lời (mục 3)
  — cả 2 trường hợp Agent Worker đều ngừng publish và gửi sentinel để Core đóng SSE; khác
  biệt là turn có **kết thúc thật sự** hay không (xem `kien-truc-agent.md` mục 6). Client bỏ
  qua dòng `data: [DONE]` cuối (không parse JSON).
- Không cache/replay: mở stream **sau khi** turn đã publish 1 số event thì mất các event đó
  (Pub/Sub không lưu lại) — client nên mở SSE **trước hoặc ngay sau** khi gọi
  `POST .../messages` (xem `api-doc.md` mục 2.1), và mở lại SSE khi resume sau khi trả lời
  câu hỏi (mục 4).

## 2. Bảng event (`type`)

| `type` | Khi nào | Payload (ngoài `type`) |
|---|---|---|
| `message.queued` | ngay sau khi Core publish turn vào `agent_request_queue`, trước khi Agent Worker nhận | `corrId`, `conversationId`, `messageId` |
| `message.steered` | user gửi thêm tin nhắn khi turn đang chạy (Steer, mục 5) | `corrId`, `conversationId`, `messageId`, `content` |
| `message.started` | Agent Worker bắt đầu xử lý turn | `corrId`, `clientMessageId?`, `conversationId`, `messageId` |
| `reasoning.step_started` | đầu 1 reasoning step | `messageId`, `conversationId`, `stepId`, `title`, `stepType?` (`default`\|`tool_call`\|`tool_ask`), `choice?` (mục 3) |
| `reasoning.step_delta` | lặp nhiều lần trong 1 reasoning step | `messageId`, `conversationId`, `stepId`, `delta` |
| `reasoning.step_completed` | cuối 1 reasoning step | `messageId`, `conversationId`, `stepId`, `stepType?`, `choice?` (mục 3) |
| `message.delta` | lặp nhiều lần, sau khi hết reasoning | `messageId`, `conversationId`, `delta` |
| `message.done` | turn kết thúc bình thường | `messageId`, `conversationId`, `reasoning?` (toàn bộ `ReasoningStep[]`), `sources?` (`ChatSource[]`) |

> Không có event `document.*` (soạn văn bản canvas qua OnlyOffice) — luồng hiện tại của dự án
> chỉ gồm chat + reasoning, chưa có tính năng agent soạn văn bản. `attachments` (tệp **user
> upload kèm tin nhắn**, khác với canvas) vẫn giữ nguyên — xem `db-diagram.md` mục 2.

**Thứ tự chuẩn 1 turn** (không steer, không hỏi lại):

```
message.queued → message.started
  → (reasoning.step_started → reasoning.step_delta* → reasoning.step_completed)  × N step
  → message.delta*
  → message.done
```

## 3. Hỏi lại user = tool call (`tool_ask`), không phải event `question` độc lập

`fe/docs/backend-contract.md` mục 3.3 (bản mô tả cũ) liệt kê 1 event `question` riêng. Nguồn
chuẩn hiện tại (`fe/features/chat/types.ts`) **không có** type này trong `FlatStreamEvent`, và
về bản chất **việc hỏi user là 1 tool call** (`ask_user`) mà Agent gọi trong lúc xử lý — xem
`kien-truc-agent.md` mục 3 — chứ không phải 1 nhánh dừng turn cấp cao. Biểu diễn ra ngoài qua
trường **`choice`** đính kèm trên `reasoning.step_started`/`reasoning.step_completed`, với
`stepType="tool_ask"`:

```json
data: {"type":"reasoning.step_completed","messageId":"msg-1","conversationId":"conv-1","stepId":"msg-1-step-2","stepType":"tool_ask","choice":{"questionId":"msg-1-q1","question":"Bạn muốn tìm hiểu khía cạnh nào?","options":[{"id":"qk1","label":"Chọn thuốc bôi theo mức độ mụn"}]}}
```

- Turn **tạm dừng (pause) ngay sau event này** — không phải **kết thúc**: Agent Worker
  `interrupt()` (LangGraph), giữ nguyên state graph qua checkpointer, chờ resume (mục 4).
  Không có `message.delta`/`message.done` theo sau **cho tới khi được resume**; Core đóng SSE
  connection hiện tại (nhận sentinel `[DONE]`) như khi kết thúc bình thường — client phải mở
  lại SSE connection mới sau khi gọi API trả lời (mục 4) để tiếp tục nhận event.
- Client nhận diện "turn đang chờ trả lời" bằng: event cuối cùng nhận được có `choice` khác
  null (`stepType="tool_ask"`), và connection đã đóng mà chưa thấy `message.done`.
- Đây là điểm khác biệt quan trọng nhất giữa 2 nguồn tài liệu FE — **tài liệu này (và mọi
  code Core) phải theo `types.ts`**, coi mô tả `question` độc lập trong `backend-contract.md`
  là lỗi thời.

## 4. Trả lời câu hỏi (`tool_ask`) — KHÔNG phải message mới, KHÔNG phải Steer

`fe/docs/backend-contract.md` mục 3.4 mô tả việc trả lời bằng cách gửi **1 POST mới** tới
`POST .../messages` kèm field `answer` — **quy ước này đã lỗi thời**, thay bằng: trả lời 1
câu hỏi đang chờ (mục 3) đi qua **endpoint riêng**, không tạo `messages` row mới, không phải
Steer:

`POST /api/v1/conversations/{conversationId}/questions/{questionId}/answer` — xem `api-doc.md`
mục 2.2 cho chi tiết request/response.

**Xử lý phía Core**:
1. Xác định `questionId` khớp câu hỏi đang chờ của conversation (được lưu khi turn tạm dừng —
   xem mục 6 phần "Persist khi tạm dừng").
2. Publish "resume request" vào `agent_request_queue`, kèm đủ thông tin để Agent Worker tìm
   đúng checkpoint đã `interrupt()` (`conversation_id` + `questionId`/`corr_id`) —
   **không** phải 1 `AgentTurnRequest` mới.
3. Agent Worker `Command(resume=answer)` (LangGraph) — graph chạy tiếp **đúng Reasoning đã
   tạm dừng** (kết quả tool `ask_user` chính là answer), cập nhật `choice.answered` trên
   reasoning step đó, rồi Step đó tiếp tục bình thường (có thể còn Reasoning khác trong cùng
   Step, hoặc kết thúc Step luôn nếu LLM không gọi thêm tool — xem `kien-truc-agent.md` mục
   0), tới khi cả turn `message.done`.
4. Client (đã gọi API answer xong) **mở lại SSE connection mới** tới cùng
   `GET .../stream` để tiếp tục nhận event từ chỗ resume.

**Vì sao không phải Steer**: Steer (mục 5) là 1 tin nhắn **mới, độc lập** với nội dung mà
Agent chưa yêu cầu — được xử lý ở Step *tiếp theo* (qua `pre_step`). Trả lời `tool_ask` là
**kết quả của 1 tool call cụ thể mà Agent đang chờ ngay trong Reasoning hiện tại** — phải nạp
lại đúng chỗ đó (resume đúng Reasoning đang dừng, không đợi tới Step sau), gọi nó là "message"
hay "steer" sẽ khiến Agent hiểu nhầm đây là 1 yêu cầu mới của user thay vì input cho tool đang
treo.

## 5. Luồng Steer message — 2 status `pending` → `queued`

Định nghĩa gốc: `fe/docs/backend-contract.md` mục 5. Khi Agent Worker đang xử lý turn
(chưa `message.done`, và **không** đang tạm dừng chờ `tool_ask` — trường hợp đó xem mục 4) mà
user gửi thêm 1 tin nhắn **mới** qua `POST /conversations/{id}/messages` (`api-doc.md` mục
2.1), tin nhắn Steer đi qua **2 trạng thái** trước khi được LLM thực sự xử lý — khớp trực
tiếp với ranh giới Step ↔ Reasoning ở `kien-truc-agent.md` mục 0:

1. **`status="pending"`** — Core lưu tin nhắn Steer vào `messages` **ngay khi nhận request**,
   publish kèm cờ `is_steer=true` vào `agent_request_queue` (**không** tạo turn mới). Tại thời
   điểm này, Step hiện tại của Agent Worker **chưa chạy xong** (còn đang lặp Reasoning, xem
   `kien-truc-agent.md` mục 0) — tin nhắn Steer **chưa** được đưa vào `messages` context của
   graph, chỉ nằm chờ.
2. **`status="queued"`** — khi Step hiện tại tự nhiên kết thúc (Reasoning cuối hết tool call)
   và graph quay lại `pre_step`, `pre_step` phát hiện có Steer đang `pending`, **append vào
   context** (`messages` của `TurnState`) — đây chính là hành động "cần append thêm message
   mới không?" ở định nghĩa Pre-step (`kien-truc-agent.md` mục 1). Ngay khi append xong, Agent
   Worker publish `message.steered` qua Redis kèm `content` tin nhắn Steer, và cập nhật status
   thành `queued` (cơ chế cập nhật DB — xem mục 6) — nghĩa là tin nhắn đã nằm trong context,
   sẵn sàng để Step tiếp theo xử lý (LLM sẽ "thấy" nó ở lần gọi kế tiếp).
3. Tin nhắn Steer **không** có status riêng cho "đã được LLM xử lý xong" — một khi đã
   `queued`, nó là 1 phần cố định của lịch sử hội thoại (giống mọi user message khác).
4. Thứ tự bắt buộc trong DB (`messages`, sắp theo `createdAt`):
   `Initial User Message` → `Steer User Message` → `Assistant Message` (chỉ 1 assistant
   message cho cả turn, dù có steer ở giữa — xem mục 6).

> Tin nhắn **mở đầu 1 turn mới** (không phải Steer) không đi qua `pending` — không có Step nào
> đang chạy để phải chờ, nên lưu thẳng `status="done"` (mục 6). Về lý thuyết có thể áp dụng
> đối xứng `queued` cho tin nhắn mở đầu turn (chờ `pre_step` của Step #1 "tiêu thụ" nó) — tài
> liệu này **chưa quyết định** việc đó, giữ nguyên `"done"` như thiết kế ban đầu; ghi nhận ở
> đây để không quên nếu sau này cần thống nhất 2 luồng.

## 6. Quy tắc persist (khi nào ghi DB)

- **User message**: persist **ngay** khi nhận request (`POST .../messages`), trước khi
  publish vào RabbitMQ. Trả lời `tool_ask` (mục 4) **không** tạo row user message mới.
  - Tin nhắn mở đầu turn mới: `status="done"` ngay (mục 5, ghi chú cuối).
  - Tin nhắn Steer: `status="pending"` lúc lưu — **update** (không tạo row mới) thành
    `status="queued"` khi `pre_step` thực sự append vào context (mục 5), qua cùng cơ chế
    upsert `agent_response_queue` mô tả bên dưới cho assistant message.
- **Assistant message — persist khi turn kết thúc** (`message.done`): trong lúc streaming
  (`reasoning.*`, `message.delta`), nội dung assistant **chưa có row trong `messages`**, chỉ
  tồn tại tạm trong bộ nhớ Agent Worker rồi stream qua Redis.
- **Assistant message — persist sớm khi tạm dừng chờ `tool_ask`** (mục 3): đây là **ngoại lệ**
  của quy tắc trên, cần thiết vì `MessageStatus` phía FE có giá trị `"question"` — nghĩa là
  FE cần thấy được trạng thái "đang chờ trả lời" kể cả sau khi **reload trang** (checkpointer
  của LangGraph chỉ phục vụ resume phía Agent, FE/Core không đọc được nó qua DB). Cơ chế:
  - Khi node `reasoning` gọi `interrupt()` (gặp tool `ask_user`), Agent Worker publish 1
    message vào `agent_response_queue` (cùng queue dùng cho kết quả cuối) với
    `status="question"`, `content` rỗng/tạm, `metadata.reasoning` = các reasoning step đã có
    (kể cả reasoning step `tool_ask`).
  - Core consume `agent_response_queue`, **upsert** (insert nếu chưa có, update nếu đã có)
    `messages` row theo `id=messageId` — cùng `messageId` Agent Worker sinh lúc
    `message.started` (mục 3, `async-api-doc.md`).
  - Khi turn thực sự kết thúc (resume xong, `message.done`), Agent Worker publish lại vào
    `agent_response_queue` với `status="done"` + nội dung đầy đủ — Core **update cùng row**
    (không tạo row mới).
  - **Cùng cơ chế upsert này** dùng để cập nhật `status="pending" → "queued"` cho tin nhắn
    Steer (mục 5): khi `pre_step` append 1 Steer đang chờ vào context, Agent Worker publish 1
    message vào `agent_response_queue` với `id` = id tin nhắn Steer đó (đã có sẵn — Core sinh
    lúc lưu ở mục 5 bước 1, gửi kèm trong `AgentTurnRequest`/resume request) và
    `status="queued"` — Core update đúng row đó, không tạo mới.
- Hệ quả: `GET /conversations/{id}/messages` (REST, `api-doc.md` mục 1.3) có thể trả về 1
  assistant message với `status="question"` (đang chờ) — FE dùng field này để hiển thị lại
  UI hỏi/chọn sau khi reload, thay vì chỉ trả về các turn đã hoàn tất như thiết kế trước đó.

## 7. Việc còn lại (chưa implement)

| Hạng mục | Trạng thái |
|---|---|
| `sources` (`ChatSource[]`) | Chưa có — cần tool tra cứu tài liệu tham chiếu thật (chưa có tool nghiệp vụ nào ngoài `ask_user`) |
| Tool nghiệp vụ (ngoài `ask_user`) | Node `reasoning` đã có nhánh xử lý tool "chưa hỗ trợ" (trả lỗi cho LLM tự retry) — chưa cài tool thật nào |
| Race Steer vào đúng lúc turn kết thúc | Đã ghi nhận ở cảnh báo đầu file — chưa xử lý |
| Checkpointer production | Đang dùng `InMemorySaver` (dev) — cần Postgres/Redis-backed khi chạy nhiều Agent Worker instance (`kien-truc-agent.md` mục 3) |
| Celery hoá worker | Xem `core/README.md` mục "Agent worker — Celery (định hướng)" — chưa làm |
| Global exception handler (`{"error": {...}}`) | Chưa có — `api-doc.md` mục 2.2 dùng `HTTPException` mặc định tạm thời |

Backlog refactor `app/agent/worker.py` (và graph khi đủ theo `kien-truc-agent.md`) — chưa đổi
code ở bước viết tài liệu này.
