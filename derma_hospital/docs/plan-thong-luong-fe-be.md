# Thông luồng BE ⇄ Worker ⇄ FE: real token streaming, `agent_response_queue`, fix contract FE

## Context

Hiện tại 3 mảng ghép nối Core/Agent Worker/FE đều lệch so với thiết kế đã document:

1. **Streaming "giả"**: `worker.py` gọi `llm.ainvoke()` (1 lần, chặn tới khi xong) rồi mới cắt
   `content` thành chunk 24 ký tự để giả lập `reasoning.step_delta` — nghĩa là FE chỉ thấy
   "stream" SAU KHI LLM đã trả lời xong hoàn toàn, không phải token thật theo thời gian thực.
2. **`agent_response_queue` chưa dùng**: hằng số đã khai báo trong `constants.py` nhưng
   `worker.py` vẫn ghi thẳng vào Postgres qua `AsyncSessionLocal`/`MessageRepository` — đúng
   như `async-api-doc.md` mục 6 đã tự nhận là "sai khác", vì Worker và Core hiện dùng chung 1
   package Python nên chưa lộ vấn đề, nhưng không đúng với kiến trúc 2 service tách biệt.
3. **FE gửi sai contract thật của Core**: `fe/services/apiAdapters.ts` vẫn implement theo
   `fe/docs/backend-contract.md` v1.5 (đã bị chính `async-api-doc.md` của BE tuyên bố lỗi
   thời) — thiếu `clientMessageId` bắt buộc, nesting sai `attachments`/`selection`, trả lời
   `tool_ask` qua `POST /messages` thay vì endpoint `/questions/{id}/answer` riêng, và (phát
   hiện thêm khi review) **toàn bộ interface DTO trong `apiAdapters.ts` dùng snake_case
   (`created_at`, `conversation_id`, `selection_ref`...) trong khi backend luôn trả camelCase**
   (`CamelModel` ở `core/app/dto/common.py` áp dụng cho MỌI response DTO) — nghĩa là chạy với
   Core thật (không phải mock) sẽ đọc `undefined` cho gần hết field.

Đã xác nhận với user 3 quyết định phạm vi: (a) sửa luôn code FE, (b) đổi sang streaming token
thật từ LLM (không giữ giả lập), (c) implement `agent_response_queue` đúng theo thiết kế đã
document. Plan này chốt cách làm cụ thể cho cả 3, đã verify tính khả thi bằng 1 spike thật với
`langgraph` cài trong `core/.venv` (xác nhận `get_stream_writer()` + `stream_mode=["values",
"custom"]` cho ra đúng thứ tự `(mode, payload)` cần dùng).

**Thứ tự thực hiện: C → B → A** (fix FE trước vì đó là điều kiện để test end-to-end thật với
Core không cần mock; B trước A vì B cơ chế đã được document rõ, rủi ro thấp hơn, test độc lập
được bằng cách publish tay 1 message vào `agent_response_queue`).

---

## C. Fix contract Frontend (làm trước)

### C.1 `fe/services/apiAdapters.ts` — viết lại toàn bộ interface wire DTO sang camelCase

- `ApiConversation`: `created_at`/`updated_at` → `createdAt`/`updatedAt`. Sửa `toConversation()`.
- Gộp `ApiUserMessageMetadata`/`ApiAssistantMessageMetadata` thành 1 `ApiMessageMetadata` khớp
  `MessageMetadataDto` (`core/app/dto/message.py`) verbatim, camelCase:
  `{ reasoning?, selectionRef?, attachments?, choice?, sources?, isOptionResponse? }`. Bỏ
  `document` (chưa có ở backend — `async-api-doc.md` mục 2/7 xác nhận chưa implement).
- `ApiReasoningStep`: thêm field `choice?: MessageChoice | null` đang bị thiếu (map từ
  `ReasoningStepDto.choice`).
- `ApiSelectionRef`: `ref_id`→`refId`; bỏ `version_no` (backend `MessageSelectionRefDto`
  không có field này — chỉ giữ `versionNo` ở type nội bộ FE nếu chỗ khác cần, không gửi/nhận
  qua wire). Lưu ý thêm: backend `MessageSelectionRefDto.source` là `Literal["message"]` — gửi
  `"canvas"`/`"document"` sẽ bị 422; tạm chấp nhận vì tính năng canvas/document chưa có ở
  backend, note lại trong code bằng comment.
- `ApiChatMessage`: `conversation_id`→`conversationId`, `created_at`→`createdAt`, `role` chỉ
  còn `"user"|"assistant"`, bỏ `message_type` (không tồn tại ở backend).
- `toChatMessage()`: đọc field camelCase ở trên, map `choice` theo từng reasoning step, map
  `isOptionResponse`, và **sửa lỗi chính đã yêu cầu**: `status: a.status` thay vì hard-code
  `"done"` (để UI khôi phục đúng trạng thái `"question"`/`"pending"`/`"queued"` khi F5 giữa
  chừng — theo đúng gợi ý ở `async-api-doc.md` mục 6).
- `toSendMessageBody()` + `ApiSendMessageBody`: đổi thành
  `{ clientMessageId, content, modelId?, attachments?, selection? }` — bỏ hẳn wrapper
  `metadata` và field `answer` (backend `SendMessageInput` — `core/app/dto/message.py` — không
  có 2 field này, đang bị Pydantic âm thầm bỏ qua). Set
  `clientMessageId: input.clientMessageId ?? input.corrId` để chỗ gọi `sendMessage()` hiện tại
  (chỉ truyền `corrId`) tự động hết lỗi thiếu field bắt buộc mà không cần sửa call site đó.

### C.2 `fe/services/endpoints.ts`

Thêm:
```ts
answerQuestion: (conversationId: string, questionId: string) =>
  `/conversations/${conversationId}/questions/${questionId}/answer`,
```

### C.3 `fe/features/chat/types.ts`

Thêm vào interface `ChatService`:
```ts
answerQuestion(input: {
  conversationId: string;
  questionId: string;
  optionId: string;
  label: string;
  custom?: boolean;
}): Promise<void> | void;
```

### C.4 `fe/services/chat.sse.ts`

`sendMessage()` hiện tại: mở SSE (`fetch GET .../stream`) TRƯỚC, rồi mới POST, rồi đọc stream
tới khi đóng — tránh mất event đầu (đã có comment giải thích rõ trong code). `answerChoice`
cần CHÍNH XÁC pattern này (mở stream trước, vì kết nối SSE cũ đã đóng lúc turn pause ở
`tool_ask`) nhưng hiện đang gọi thẳng `sendMessage()` với endpoint/body sai — đây là lỗ hổng
thực sự (turn resume xong sẽ không có ai đang nghe stream).

Refactor: tách phần đọc SSE dùng chung (dòng ~93–145) thành 1 helper nội bộ
`_streamThenPost(conversationId, postFn)`, dùng lại cho cả `sendMessage` và
`answerQuestion` mới:
```ts
async answerQuestion(input) {
  await _streamThenPost(input.conversationId, () =>
    api.post(endpoints.answerQuestion(input.conversationId, input.questionId), {
      questionId: input.questionId,
      optionId: input.optionId,
      label: input.label,
      custom: input.custom,
    })
  );
},
```
Field trong body khớp verbatim `MessageAnswerDto` (`core/app/dto/message.py`): `questionId,
optionId, label, custom`.

### C.5 `fe/features/chat/store.ts` — `answerChoice()` (~dòng 657–738)

- Bỏ việc dựng `questionText`/`synthesizedContent`.
- Giữ nguyên phần patch optimistic UI hiện có (`status:"streaming"`, `isOptionResponse:true`,
  gắn `answered` vào `choice`/`reasoning[].choice`) — phần này đúng, không phải bug.
- Thay lời gọi `chatService.sendMessage({..., content: synthesizedContent, answer:{...}})`
  bằng `chatService.answerQuestion({ conversationId: convId, questionId:
  target.choice.questionId, optionId: answer.optionId, label: answerLabelText, custom:
  answer.custom })`, giữ nguyên khối `.catch(...)` xử lý lỗi hiện có.

### C.6 `fe/services/mock/mockChatService.ts`

Thêm stub `answerQuestion` tối thiểu (mô phỏng tương tự cách `sendMessage` mock hiện giả lập
event) để object vẫn khớp interface `ChatService` khi chạy `NEXT_PUBLIC_USE_MOCK=true`.

### Ghi nhận, KHÔNG sửa trong plan này (dọn sau, ưu tiên thấp)

- `ConversationStreamEvent`/`normalizeStreamEvent()` trong `store.ts` (~dòng 88–166): dead
  code, backend không bao giờ tạo ra shape lồng này.
- `ReasoningStatusType`'s `"reasoning_step_delta"` (gạch dưới) khác `"reasoning.step_delta"`
  (dấu chấm) thật trên wire — chỉ nằm trong nhánh dead code trên, vô hại.

---

## B. Implement `agent_response_queue` (Worker → RabbitMQ → Core persist)

Đúng theo thiết kế đã ghi ở `core/docs/async-api-doc.md` mục 6: Worker không còn ghi DB trực
tiếp, chỉ publish; Core là writer duy nhất của bảng `messages` cho các path này.

### B.1 Schema mới — `core/app/agent/schemas.py` (cạnh `TurnRequest`, cùng kiểu discriminator `type`)

```python
class AgentResponseMessage(BaseModel):
    """Payload agent_response_queue (Worker -> Core); Core là consumer duy nhất, làm
    upsert DB (docs/async-api-doc.md mục 6).
    - type="assistant_upsert": ghi/đè dòng assistant message của cả turn
      (status="question" lúc tạm dừng, "done" lúc kết thúc).
    - type="steer_status": cập nhật status 1 dòng Steer đã tồn tại (pending -> queued).
    """
    type: Literal["assistant_upsert", "steer_status"]
    conversation_id: str
    message_id: str  # id dòng cần upsert/update

    content: str | None = None  # type="assistant_upsert"
    reasoning: list[dict[str, Any]] | None = None  # [ReasoningResult.model_dump(mode="json"), ...]
    status: Literal["question", "done", "queued"] | None = None
```

### B.2 `core/app/agent/worker.py`

- `_persist_assistant()`: thay `AsyncSessionLocal()`/`MessageRepository.upsert_assistant()`
  bằng publish `AgentResponseMessage(type="assistant_upsert", ...)` vào `AGENT_RESPONSE_QUEUE`
  qua `rabbitmq_client.publish(...)` (dùng lại `RabbitMQClient.publish()` có sẵn ở
  `app/infra/rabbitmq_client.py`, giống hệt cách `MessageService._publish()` publish
  `TurnRequest`).
- Bỏ import `AsyncSessionLocal`, `MessageRepository` khỏi file này (không còn dùng ở đâu nữa
  sau B.2+B.3).
- **Bỏ** dòng `await redis_delete(AGENT_ACTIVE_TURN_KEY.format(...))` cuối `_drive_graph` —
  chuyển sang consumer mới ở Core (B.4), vì Core là bên đã SET key này (`start_new_turn`) nên
  để Core tự dọn khi đã persist xong là đối xứng và tránh 1 khoảng race nhỏ.
- Cập nhật lại docstring đầu file (không còn đúng phần "đơn giản hoá ghi thẳng DB").

### B.3 `core/app/agent/graph.py` — `pre_step()` (dòng ~58–88)

- **Đọc** (`repo.list_pending_steers`) giữ nguyên, vẫn đọc DB trực tiếp — không phải vấn đề
  ownership, và redesign phần đọc Steer nằm ngoài phạm vi plan này.
- **Ghi** (`repo.update_status(steer.id, "queued")`) đổi thành publish
  `AgentResponseMessage(type="steer_status", message_id=steer.id, status="queued")` vào
  `AGENT_RESPONSE_QUEUE` (import `rabbitmq_client`, `AGENT_RESPONSE_QUEUE`,
  `AgentResponseMessage` vào `graph.py`). Bỏ `db.commit()` tương ứng (session giờ chỉ đọc).
- Lý do publish trực tiếp trong `pre_step` thay vì qua 1 field mới trong `TurnState` để
  `worker.py` publish hộ: `pre_step` chỉ chạy ĐÚNG 1 LẦN mỗi Step nên publish tại chỗ không bị
  lặp; nếu để `worker.py` đọc lại field state mỗi lần state "values" đi qua sẽ dễ publish lặp
  nhiều lần trong cùng 1 Step (field state không tự reset về rỗng giữa các "values" chunk của
  cùng Step — đây là đặc điểm đã có sẵn của field tương tự `last_steer_batch`, không phải bug
  mới tạo ra, chỉ là lý do tại sao KHÔNG chọn cách đó).

### B.4 Module mới — `core/app/agent/response_consumer.py`

```python
"""Core-side consumer cho agent_response_queue (async-api-doc.md mục 6) — Core là sole
writer của bảng messages cho các path này; Agent Worker chỉ publish."""
import json
from aio_pika.abc import AbstractIncomingMessage
from app.agent.schemas import AgentResponseMessage
from app.core.constants import AGENT_ACTIVE_TURN_KEY, AGENT_RESPONSE_QUEUE
from app.db.session import AsyncSessionLocal
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import delete as redis_delete
from app.repositories.message_repository import MessageRepository


async def _on_response(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            msg = AgentResponseMessage.model_validate(json.loads(message.body))
        except Exception as exc:  # noqa: BLE001
            print(f"[Response Consumer] invalid payload: {exc}")
            return

        async with AsyncSessionLocal() as db:
            repo = MessageRepository(db)
            if msg.type == "assistant_upsert":
                await repo.upsert_assistant(
                    message_id=msg.message_id, conversation_id=msg.conversation_id,
                    content=msg.content or "", status=msg.status or "done",
                    extra={"reasoning": msg.reasoning or []},
                )
            else:
                await repo.update_status(msg.message_id, msg.status or "queued")
            await db.commit()

        if msg.type == "assistant_upsert" and msg.status == "done":
            await redis_delete(AGENT_ACTIVE_TURN_KEY.format(conversation_id=msg.conversation_id))


async def start_consuming() -> None:
    await rabbitmq_client.consume(AGENT_RESPONSE_QUEUE, _on_response)
```

Tái dùng nguyên `MessageRepository.upsert_assistant`/`update_status` đã có (`core/app/
repositories/message_repository.py`) — không cần thêm method mới ở repo.

### B.5 Wire vào `core/main.py`

Trong `lifespan()`, ngay sau `await rabbitmq_client.connect()`, thêm
`await start_consuming()` (import từ `app.agent.response_consumer`). `RabbitMQClient.consume()`
(`app/infra/rabbitmq_client.py`) chỉ đăng ký callback rồi return ngay (không block) — an toàn
gọi trong lifespan trước `yield`, không cần vòng lặp chờ như `worker.py`'s `main()` vì uvicorn
tự giữ event loop sống.

---

## A. Real LLM token streaming (làm sau cùng)

### A.1 `core/app/agent/graph.py` — `_run_llm()` (dòng ~121–156)

Import `from langgraph.config import get_stream_writer`. Node gọi `writer()` để publish
"trực tiếp theo đúng shape wire event" (cùng field `messageId/conversationId/stepId/delta/
title/stepType` mà Redis event đã dùng) — nhờ vậy `worker.py` chỉ cần forward gần như
nguyên văn, không cần tầng map tên riêng:

```python
async def _run_llm(state: TurnState, step_id: str, step_index: int) -> dict[str, object]:
    writer = get_stream_writer()
    base = {"messageId": state["message_id"], "conversationId": state["conversation_id"], "stepId": step_id}
    writer({"type": "reasoning.step_started", "title": "Suy luận", "stepType": "default", **base})

    llm = get_llm_with_tools(ALL_TOOLS)
    full: AIMessageChunk | None = None
    try:
        async for chunk in llm.astream([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]):
            full = chunk if full is None else full + chunk
            if chunk.content:
                writer({"type": "reasoning.step_delta", "delta": str(chunk.content), **base})
    except NotImplementedError:
        full = None  # provider/model không hỗ trợ streaming -> fallback dưới

    if full is None:
        response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        if response.content:
            writer({"type": "reasoning.step_delta", "delta": str(response.content), **base})
    else:
        response = AIMessage(content=full.content, tool_calls=full.tool_calls)  # chuẩn hoá về AIMessage thường trước khi vào checkpoint

    writer({"type": "reasoning.step_completed", "stepType": "default", **base})
    # ... phần còn lại GIỮ NGUYÊN như hiện tại: build `ReasoningResult`, return dict update
    # (messages/current_step/step_count/just_closed_step[, steps/final_answer]) — state vẫn
    # là nguồn sự thật để persist/lịch sử, streaming chỉ là kênh phụ song song.
```

Lưu ý triển khai:
- `writer()` là no-op an toàn khi graph được drive với `stream_mode` không có `"custom"` —
  gọi vô điều kiện không ảnh hưởng chỗ khác đang chạy graph.
- Chuẩn hoá `AIMessageChunk` về `AIMessage` thường trước khi đưa vào state — tránh đẩy
  `BaseMessageChunk` vào checkpoint.
- **Cần verify thực tế lúc code**: provider hiện tại `AGENT_MODEL=google_genai:gemini-2.5-
  flash-lite` (`core/.env`, qua `langchain-google-genai`) — kiểm tra `.astream()` có populate
  `tool_calls` tăng dần qua `tool_call_chunks` hay chỉ ở chunk cuối cùng; cách accumulate bằng
  `full = chunk if full is None else full + chunk` rồi đọc `full.tool_calls` sau vòng lặp là
  pattern chuẩn của LangChain, nhưng vẫn nên test tay 1 lần với tool `ask_user` để chắc chắn
  `step_continues` vẫn được tính đúng.

`_run_tool()`: KHÔNG thêm early "tool started" custom event trong plan này (chưa có tool
`requires_wait=False` thật nào để test) — để lại 1 comment ngắn trong code rằng khi có tool
chạy lâu thật, dùng đúng pattern `get_stream_writer()` này trước `await spec.run(tool_call)`.

### A.2 `core/app/agent/worker.py` — `_drive_graph()` (dòng ~93–172)

```python
async for mode, chunk in agent_graph.astream(input_or_command, config, stream_mode=["values", "custom"]):
    if isinstance(chunk, dict) and "__interrupt__" in chunk:
        interrupted = True
        break

    if mode == "custom":
        await _emit(channel, chunk)  # đã đúng shape wire sẵn từ graph.py — forward gần như nguyên văn
        if chunk.get("type") == "reasoning.step_completed":
            published.add(chunk["stepId"])  # để vòng lặp "values" bên dưới không publish lại
        continue

    state: TurnState = chunk
    last_state = state
    # ... phần còn lại GIỮ NGUYÊN (vòng lặp last_steer_batch, vòng lặp _all_reasoning) ...
```

Điểm quan trọng:
- **Phát hiện interrupt**: kiểm tra `"__interrupt__" in chunk` TRƯỚC khi rẽ theo `mode`, áp
  dụng trên `chunk` đã unpack (không phải tuple thô) — spike đã làm trong session này CHƯA
  test trường hợp interrupt dưới `stream_mode=["values","custom"]`, **cần verify thực tế lúc
  code** (thêm tạm `print(mode, chunk)` khi test kịch bản `ask_user`, xác nhận interrupt vẫn
  đi kèm `mode="values"` như hiện tại).
- **Không publish trùng**: vòng lặp `_all_reasoning(state)` + `if r.step_id not in published`
  hiện có GIỮ NGUYÊN — reasoning kiểu `tool_call`/`tool_ask` (không stream qua `custom`) vẫn
  được `_publish_reasoning()` publish 1 lần như cũ; reasoning `default` (LLM) bị bỏ qua ở đây
  vì `step_id` đã có trong `published` từ nhánh `custom` phía trên.
- **`DELTA_CHUNK_SIZE`/`_publish_reasoning()` KHÔNG xoá** — vẫn cần cho: (a) reasoning
  `tool_call`/`tool_ask` (không có "token" thật để stream), (b) đoạn `message.delta` cuối lặp
  lại `final_answer` (vốn đã là bản copy của reasoning cuối cùng — đã stream thật rồi, đoạn
  lặp lại này không đại diện token mới nên giữ nguyên cách cũ là đúng, không cần đổi).

---

## Files cần sửa (tóm tắt)

| File | Thay đổi |
|---|---|
| `fe/services/apiAdapters.ts` | Viết lại toàn bộ interface wire DTO sang camelCase, sửa `toChatMessage`/`toSendMessageBody` |
| `fe/services/endpoints.ts` | Thêm `answerQuestion(conversationId, questionId)` |
| `fe/features/chat/types.ts` | Thêm `answerQuestion` vào `ChatService` |
| `fe/services/chat.sse.ts` | Tách `_streamThenPost` helper, thêm `answerQuestion` |
| `fe/features/chat/store.ts` | `answerChoice()` gọi `chatService.answerQuestion(...)` thay vì `sendMessage` |
| `fe/services/mock/mockChatService.ts` | Stub `answerQuestion` |
| `core/app/agent/schemas.py` | Thêm `AgentResponseMessage` |
| `core/app/agent/worker.py` | `_persist_assistant` publish queue thay vì ghi DB; bỏ `redis_delete` active-turn key; `_drive_graph` dùng `stream_mode=["values","custom"]` |
| `core/app/agent/graph.py` | `pre_step` publish `steer_status` thay vì `update_status` trực tiếp; `_run_llm` dùng `llm.astream()` + `get_stream_writer()` |
| `core/app/agent/response_consumer.py` (mới) | Consumer `agent_response_queue`, upsert DB, xoá active-turn key |
| `core/main.py` | Gọi `start_consuming()` trong `lifespan()` |

## Verify end-to-end

1. `docker-compose up -d postgres redis rabbitmq` (repo root — chỉ có infra, Core/Worker vẫn
   chạy process thường).
2. `cd core && python main.py` (port 3050); terminal khác: `cd core && python -m
   app.agent.worker`.
3. `cd fe && NEXT_PUBLIC_USE_MOCK=false pnpm dev`.
4. Test riêng B (không cần FE): `POST /conversations` lấy `conversationId` → mở
   `curl -N localhost:3050/api/v1/conversations/{id}/stream` ở 1 terminal → `POST
   /conversations/{id}/messages` với `{"clientMessageId":"c1","content":"..."}` → theo dõi
   thứ tự event `message.queued → message.started → reasoning.step_started → nhiều
   reasoning.step_delta (rải rác theo thời gian thực, KHÔNG dồn cục 1 lúc — xác nhận A hoạt
   động) → reasoning.step_completed → message.delta* → message.done → [DONE]`. `psql -c
   "select id,status,content from messages where conversation_id='...'"` xác nhận row tồn tại
   và `status='done'` dù `worker.py` không còn đụng Postgres — bằng chứng B hoạt động.
5. Test pause/resume (`ask_user`, kiểm A's `tool_ask` + B's `status="question"`): tạo prompt
   khiến model gọi `ask_user` → stream kết thúc bằng `[DONE]` ngay sau
   `reasoning.step_completed` có `choice` → `psql` thấy `status='question'` → gọi `POST
   .../questions/{questionId}/answer` → mở lại `curl -N .../stream` mới → xác nhận resume tới
   `message.done` → `psql` thấy `status='done'`.
6. Test Steer (kiểm B's `steer_status`): gửi tin nhắn thứ 2 vào cùng conversation khi turn
   đang chạy → `psql` thấy row mới `status='pending'` rồi chuyển `'queued'` khi `pre_step`
   chạy → SSE thấy `message.steered`.
7. Test FE thật (kiểm toàn bộ C): dùng UI thật (không mock) — gửi tin nhắn, F5 giữa chừng lúc
   đang có `tool_ask` và xác nhận lịch sử khôi phục đúng trạng thái câu hỏi đang chờ; trả lời
   câu hỏi qua UI và xác nhận tự tiếp tục stream tới xong không cần F5; gửi Steer qua UI xác
   nhận không bị lỗi 422 (xác nhận fix `clientMessageId`).