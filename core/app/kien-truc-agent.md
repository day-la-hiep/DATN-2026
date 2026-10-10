# Kiến trúc Agent

Agent gồm **hai graph** nối nhau: **chat graph** (lọc intent, trả lời luôn khi được) và **graph tiền chẩn đoán** (lập luận có cấu
trúc, tra cứu, hỏi lại người dùng, kiểm soát bằng chứng). Graph tiền chẩn đoán chạy bằng **`create_agent` của LangChain**
(`langchain.agents`, nền LangGraph): vòng lặp "gọi LLM ⇄ gọi tool", thực thi tool, checkpoint và human-in-the-loop do thư viện lo; code
của mình chỉ cắm thêm **tool**, **middleware** và **system prompt**. Chat graph là một `StateGraph` nhỏ (2 node). Không có khái niệm
Step / Pre-step / Reasoning riêng.

Xem thêm: [`docs/module/chat.md`](../../docs/module/chat.md) (luồng chat từ FE tới agent),
[`docs/overview/system-overview.md`](../../docs/overview/system-overview.md) (toàn hệ thống),
[`kien-truc-memory.md`](kien-truc-memory.md) (memory), skill `experiment-agent-flow` (thử prompt / tool).

## 1. Khái niệm

| Khái niệm | Là gì | Nằm ở đâu |
|---|---|---|
| **Turn** | Một lần agent xử lý **một tin nhắn** của người dùng: từ lúc worker nhận request tới khi trả lời xong hoặc tạm dừng để hỏi lại. Chạy bằng một lần `agent_graph.astream(...)`. | `agent/turn.py` |
| **Chat graph** | Graph ngoài cùng của một turn: node `triage` (lọc intent) rồi, nếu cần, node `pre_diagnosis` gọi graph tiền chẩn đoán. Giữ checkpointer và `store` cho cả hai. | `agent/graph/chat_graph.py` |
| **Lọc intent (triage)** | Node đầu của chat graph: tin xã giao / hỏi về trợ lý / ngoài phạm vi da liễu được trả lời luôn, còn lại chuyển sang graph tiền chẩn đoán. | `agent/graph/triage.py` |
| **Graph tiền chẩn đoán** | `create_agent` + tool + middleware: vòng lặp ReAct (model trả lời → có `tool_calls` thì thực thi tool rồi gọi model tiếp → lặp tới khi model trả lời không còn tool). | `agent/graph/pre_diagnosis_graph.py` |
| **Tool** | Hàm `@tool` agent được gọi. Đăng ký trong `ALL_TOOLS`. | `agent/tools/` |
| **Middleware** | Hook quanh lần gọi model / tool (chọn model, chèn memory, ép lập luận, phát event). | `agent/middleware/` |
| **Context** | `AgentContext` — dữ liệu riêng của một turn (`user_id`, `conversation_id`, `message_id`, ảnh đính kèm, model, danh sách bước đã ghi). | `agent/context/agent_context.py` |
| **Thread** | `thread_id` của checkpointer = `conversation_id`: mọi turn của một hội thoại nối tiếp trong cùng một lịch sử `messages`. | `agent/graph/chat_graph.py::config_for` |

```
chat graph:   START ──▶ triage ──answer──▶ END                (trả lời luôn)
                           │
                           └─diagnose / lỗi / có ảnh──▶ pre_diagnosis ──▶ END
                                                          │
graph tiền chẩn đoán (create_agent):  model ⇄ tools ... (record_reasoning, hybrid_retrieval + semantic_search / keyword_search / knowledge_graph_search chuyên biệt, ask_user...)
```

Một turn **không có số bước cố định**: model quyết định gọi tool nào, mấy lần; turn kết thúc khi model
trả lời mà không gọi tool nữa.

## 2. Luồng một turn

```
FE ──POST /messages──▶ Core ──publish──▶ RabbitMQ agent_request_queue
                         │                         │
                         │                         ▼
                         │                  Agent Worker (agent/worker.py)
                         │                  khoá theo conversation_id
                         │                         │
                         │                         ▼
                         │                  handle_turn / handle_resume (agent/turn.py)
                         │                  agent_graph.astream(updates + custom)
                         │                         │
                         │      ┌──────────────────┼───────────────────────┐
                         │      ▼                  ▼                       ▼
                         │  token LLM        middleware phát          tool ask_user
                         │  message.delta    message.tool_result      interrupt() → tạm dừng
                         │      │            message.thinking                │
                         │      └────────────▶ Redis Pub/Sub ◀───────────────┘
                         │                         │
        SSE ◀──forward───┘◀────────────────────────┘
                                                   │ xong / hỏi lại / lỗi
                                                   ▼
                                    finish_turn (agent/publisher.py)
                                    event cuối + [DONE] + AgentResponseMessage
                                                   │
                                                   ▼
                          RabbitMQ agent_response_queue ──▶ Core ghi Postgres
                                                  (app/workers/agent_response_consumer.py)
```

- Worker **không ghi Postgres**; Core là nơi duy nhất upsert bảng `messages`.
- Core chặn tin mới khi hội thoại còn turn đang chạy (khoá Redis `AGENT_ACTIVE_TURN_KEY`); worker có thêm
  một `asyncio.Lock` theo `conversation_id` làm lớp bảo vệ cuối, vì `create_agent` không hỗ trợ hai lần
  `ainvoke()` đồng thời trên cùng `thread_id`.

## 3. Thành phần trong `core/agent/`

| File | Vai trò |
|---|---|
| `worker.py` | Tiến trình riêng: consume `agent_request_queue`, khoá theo hội thoại, gọi `handle_turn` hoặc `handle_resume`. |
| `turn.py` | Dựng `AgentContext`, chạy `astream`, forward token, kết thúc turn (xong / hỏi lại / lỗi). |
| `graph/chat_graph.py` | Chat graph: `build_chat_graph()`, `agent_graph`, `config_for()`. Node `pre_diagnosis` gọi graph tiền chẩn đoán, chuyển tiếp token qua kênh `custom` và truyền lại việc xoá tin nhắn (`RemoveMessage`) của middleware vào state của chat graph. |
| `graph/triage.py` | Node `triage`: một lần gọi LLM ngắn (`prompt/triage.py`) quyết định `answer` / `diagnose`. |
| `graph/pre_diagnosis_graph.py` | `ALL_TOOLS`, `default_middleware()`, `build_pre_diagnosis_graph()` gọi `create_agent(model, tools, system_prompt, middleware, context_schema)`. |
| `graph/common.py` | Hằng số dùng chung của middleware: `TOOL_DISPLAY_NAMES`, giới hạn thử lại, schema critic. |
| `middleware/model.py` | Middleware quanh lần gọi model. |
| `middleware/tool.py` | Middleware quanh lần gọi tool (`emit_tool_result`). |
| `tools/` | Mỗi file một (nhóm) tool; `ask_user.py` là tool hỏi lại người dùng. |
| `prompt/orchestrator.py` | `SYSTEM_PROMPT`: nguyên tắc bằng chứng, khung quyết định, cách chọn tool, ngân sách tool. |
| `llm.py` | `get_model()` — khởi tạo model theo `provider:model` (OpenRouter, DeepSeek, Gemini...). |
| `agent/publisher.py` | `emit` / `finish_turn`: event cuối + sentinel `[DONE]` + `AgentResponseMessage` lên RabbitMQ. |
| `app/workers/agent_response_consumer.py` | Chạy **trong Core**: nhận `AgentResponseMessage` và ghi `messages`. |
| `dto/schemas.py` | `TurnRequest` (Core → worker), `AgentResponseMessage` (worker → Core). |

## 3b. Chat graph và lọc intent

`chat_graph.py` là `StateGraph` hai node, state `ChatState` (`messages` + `route`):

- **`triage`** (`graph/triage.py`): một lần gọi LLM ngắn (`prompt/triage.py`, structured output `{route, reply}`) nhìn tin mới nhất + 6 tin
  gần nhất. `route="answer"` (chào hỏi, cảm ơn, tạm biệt, hỏi về trợ lý, ngoài phạm vi da liễu) thì thêm `reply` vào `messages` và kết thúc
  turn. `diagnose`, **lỗi LLM, reply rỗng, tin có ảnh** (`[Ảnh đính kèm]`, luật cứng không gọi LLM) thì sang `pre_diagnosis` — mặc định luôn
  về phía an toàn. Model: `AGENT_TRIAGE_MODEL` (rỗng = model của hội thoại); tắt hẳn: `AGENT_TRIAGE_ENABLED=false` (khi đó chat graph không có
  node `triage`).
- **`pre_diagnosis`**: chạy graph tiền chẩn đoán trên `messages`. Ba điều nó phải làm vì graph con nằm trong một node: (1) truyền tiếp
  `config` để `interrupt()` của `ask_user` và checkpoint namespace hoạt động; (2) đọc stream của graph con và chuyển token model chính qua
  kênh `custom` (gọi `ainvoke` trong node thì token không đi tiếp ra ngoài); (3) trả về cả các `RemoveMessage` — middleware của graph con xoá
  tin `AIMessage` có `tool_calls` mồ côi, mà reducer `add_messages` của chat graph không tự xoá tin vắng mặt.

Khi resume sau `ask_user`, `Command(resume=...)` đi vào chat graph và tiếp tục đúng node `pre_diagnosis`; `triage` không chạy lại.

## 4. Middleware

Middleware của **graph tiền chẩn đoán**, thứ tự trong `default_middleware()` (`pre_diagnosis_graph.py`):

| Middleware | Loại | Làm gì |
|---|---|---|
| `select_model` | `wrap_model_call` | Đổi model theo `AgentContext.model` (model chọn theo từng hội thoại, `AGENT_MODEL_CHOICES`). **Phải đứng đầu** để các middleware sau thấy đúng model. |
| `inject_long_term_memory` | `wrap_model_call` | Tìm memory dài hạn liên quan tin nhắn gần nhất rồi chèn vào system message (`tools/memory.py`). |
| `force_reasoning` | `wrap_model_call` | Ngay sau một đợt kết quả tool, ép model gọi `record_reasoning` trước khi đi tiếp. |
| `enforce_initial_reasoning` | `after_model` | Lưới an toàn: model chưa lập luận mà đã trả lời / gọi tool thì bắt làm lại (tối đa `MAX_REASONING_RETRIES`, hết lượt thì cho qua). |
| `evidence_rules` | `wrap_model_call` | Lượt đã tra cứu (`hybrid_retrieval`, `semantic_search`, `keyword_search`, `knowledge_graph_search`, web) mà **không có bằng chứng** (không có đoạn sách `source="book"`, không có trang web; quan hệ đồ thị và kết quả ảnh không tính) thì thêm quy tắc cứng vào system prompt trước mỗi lần gọi model: không nêu tên bệnh / xếp hạng / độ tin cậy / lời khuyên điều trị, chỉ nói rõ chưa tra cứu được, nhắc lại lời người dùng, hỏi thêm hoặc khuyên khám. |
| `evidence_answer_check` | `after_model` | Lưới an toàn: câu trả lời cuối vẫn nhắc tên giả thuyết đã nêu khi không có bằng chứng thì bắt viết lại (tối đa 2 lần; bản nháp có thể đã stream ra, giới hạn đã biết). |
| `emit_tool_result` | `wrap_tool_call` | Sau mỗi tool: ghi một bước `type="tool"` vào `AgentContext.reasoning_steps` và phát `message.tool_result`. |

Đang **tắt** (có code, comment trong `default_middleware()`): `emit_reasoning_step` (phát `message.thinking`),
`critic_review` (chấm bản nháp cuối, tối đa `MAX_CRITIC_RETRIES` lần) và `SummarizationMiddleware` (tóm tắt
lịch sử dài).

`evidence_reasoning_check` (`wrap_tool_call`, đứng sau `emit_tool_result`) từ chối `record_reasoning` khi (1) có dữ kiện nguồn `"user"` không truy được về lời người dùng (kể cả câu trả lời `ask_user`; đối chiếu theo từ khoá, ngưỡng 50%) hoặc (2) có giả thuyết ở stage `after_evidence` / `final` trong khi không có bằng chứng. Schema của `record_reasoning` cũng bắt: stage `initial` không hiển thị độ tin cậy (chưa có bằng chứng), độ tin cậy "vừa"/"cao" cần ít nhất một dữ kiện từ tool/web ủng hộ, và `hypotheses` được phép rỗng ở `after_evidence` / `final`.

`record_reasoning` là tool ép lập luận có cấu trúc theo 3 giai đoạn (`initial` → `after_evidence` → `final`).
Trạng thái được **suy ra từ `messages`** của turn nên tự đúng khi resume sau `ask_user`, không có state riêng.

## 5. Hỏi lại người dùng (`ask_user`)

`ask_user` là một tool bình thường, chỉ khác là trong thân hàm gọi `langgraph.types.interrupt(...)`:

1. Model gọi `ask_user(question, options)` → `interrupt()` tạm dừng graph, LangGraph lưu checkpoint.
2. `astream` trả `__interrupt__`; `turn.py::_finish_with_question` dựng `MessageChoice`
   (`question_id = interrupt.id`), phát `message.question` và gửi `AgentResponseMessage(status="question")`.
   Turn **chưa kết thúc** — chỉ tạm dừng, khoá "active turn" của hội thoại vẫn còn.
3. Người dùng trả lời qua `POST /conversations/{id}/questions/{questionId}/answer` (không tạo tin nhắn mới).
   Core gửi một "resume request" vào `agent_request_queue`.
4. Worker chạy `handle_resume` → `astream(Command(resume=answer))`: `interrupt()` trả về đúng câu trả lời
   và turn chạy tiếp từ chỗ dừng, cùng `message_id`.

Checkpointer là `InMemorySaver` nên **chỉ dùng được khi chạy một worker** (xem mục 8).

## 6. Event realtime và dữ liệu lưu

Core forward nguyên văn các event này qua SSE (`/conversations/{id}/stream`):

| Event | Phát bởi | Ý nghĩa |
|---|---|---|
| `message.started` | `turn.py` | Bắt đầu turn. |
| `message.delta` | `turn.py` | Token của model chính: node `pre_diagnosis` đọc stream của graph con (chỉ node `model`) rồi chuyển tiếp qua kênh `custom`. Câu trả lời của `triage` không có token stream nên phát **một** delta chứa cả câu. |
| `message.tool_result` | `emit_tool_result` | Một tool vừa chạy xong (tên hiển thị, tham số, kết quả). |
| `message.thinking` | `emit_reasoning_step` (đang tắt) | Dòng tóm tắt lập luận / "Đang thực hiện: ...". |
| `message.question` | `turn.py` | Turn tạm dừng chờ trả lời `ask_user`, kèm `choice`. |
| `message.done` | `turn.py` | Turn xong (cả khi lỗi, nội dung là câu báo lỗi). |
| `[DONE]` | `publisher.py` | Sentinel đóng stream. |

**Bước (`Step`)** — những gì người dùng thấy trong khối "suy luận" — được middleware ghi vào
`AgentContext.reasoning_steps` trong lúc chạy, mỗi phần tử khớp `Step` (`app/dto/common/chat.py`) với
`type` là `default`, `tool` hoặc `thinking`. Bước của `ask_user` cũng là `tool` (có thêm `choice`).
Cuối turn danh sách này đi theo `AgentResponseMessage.reasoning`, Core lưu vào `messages.metadata`
(`reasoning`, `choice`) để tải lại hội thoại vẫn thấy được (SSE không replay).

## 7. Kết thúc turn

| Kết cục | Xảy ra khi | Phát gì |
|---|---|---|
| **Xong** | Model trả lời không còn `tool_calls`, hoặc triage trả lời luôn | `message.done`, `status="done"`, xoá khoá active turn |
| **Tạm dừng hỏi lại** | Tool `ask_user` gọi `interrupt()` | `message.question`, `status="question"`, giữ khoá active turn |
| **Lỗi** | LLM / tool ném lỗi giữa chừng (rate-limit, mạng...) | `message.done` với `_ERROR_TEXT`, `status="done"`; các bước đã tích luỹ vẫn được lưu |

Lỗi được coi là turn "done" kèm câu báo lỗi (thay vì thêm một trạng thái mới) để turn không treo vĩnh viễn
và người dùng hỏi lại được ngay.

## 8. Giới hạn đã biết

- **`InMemorySaver` / `InMemoryStore`**: checkpoint và long-term memory mất khi worker khởi động lại và
  không chia sẻ giữa nhiều worker. Chạy nhiều worker cần checkpointer / store bền (Postgres hoặc Redis).
- **Ngân sách tool nằm trong prompt**, không được code ép (khoảng 10 lần gọi tool / lượt, tối đa 3 vòng
  hỏi lại). Model không tuân thủ thì không có chặn cứng nào ngoài giới hạn đệ quy mặc định của LangGraph.
- Kết quả của agent chỉ là **gợi ý hỗ trợ, không phải chẩn đoán y khoa**; điều này nằm trong `SYSTEM_PROMPT`.

## 9. Thêm tool / middleware mới

- **Tool**: viết hàm `@tool` trong `agent/tools/`, thêm vào `ALL_TOOLS` (`pre_diagnosis_graph.py`) và thêm nhãn tiếng
  Việt vào `TOOL_DISPLAY_NAMES` (`graph/common.py`, thiếu thì hiển thị tên hàm). Nếu cần dùng `user_id`,
  ảnh... thì nhận `runtime: ToolRuntime` để đọc `AgentContext`. Cần hỏi người dùng giữa chừng: gọi
  `interrupt()` như `ask_user`. Cập nhật mục hướng dẫn chọn tool trong `SYSTEM_PROMPT`.
- **Middleware**: viết bằng `@wrap_model_call` / `@wrap_tool_call` / `@after_model`, thêm vào
  `default_middleware()`. Thứ tự là thứ tự áp dụng; `select_model` luôn đứng đầu.
- Thử nghiệm prompt / tool / middleware mà không cần API, RabbitMQ hay Postgres: skill `experiment-agent-flow`.
