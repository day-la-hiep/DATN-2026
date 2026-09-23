# Kiến trúc Agent — Turn / Step / Reasoning

Xem [`kien-truc-he-thong.md`](../../docs/kien-truc-he-thong.md) cho bức tranh toàn hệ thống, và
[`../docs/async-api-doc.md`](../docs/async-api-doc.md) cho hợp đồng SSE đầy đủ với Frontend
(bảng event, luồng Steer, luồng trả lời câu hỏi — mục 3/4/5 ở đó khớp trực tiếp với tài liệu
này).

## 0. Quy ước gốc (tóm tắt)

- Mỗi lượt trả response là **1 turn**.
- 1 turn gồm nhiều **step**.
- Trước mỗi step có **1 pre-step** để xác định:
  - Có cần append thêm message mới không?
  - Turn có thể kết thúc chưa — nếu chưa thì mới bắt đầu step mới.
- **1 step gồm nhiều reasoning.** 1 reasoning là **1 hành động duy nhất**: HOẶC gọi LLM, HOẶC
  gọi/thực thi 1 tool — **KHÔNG BAO GIỜ gộp "gọi LLM" và "gọi tool" vào chung 1 reasoning**.
  Đây là điểm hay bị hiểu nhầm nhất, nhấn mạnh lại ở mục ⭐ ngay dưới.
- **Hỏi người dùng = 1 reasoning kiểu gọi tool** (`ask_user`) — không phải 1 nhánh riêng của
  pre-step, không phải 1 message do user gửi — xem mục 3.

### ⭐ Cấu trúc lồng nhau — điểm quan trọng nhất của tài liệu này

**1 Turn chứa nhiều Step. 1 Step chứa nhiều Reasoning.** Reasoning là đơn vị nhỏ nhất và
**cũng là đơn vị lặp** — nhưng mỗi Reasoning chỉ làm **đúng 1 việc**:

```
╔═══════════════════════════════════════════════════════════════╗
║ TURN  — 1 lượt xử lý 1 tin nhắn user                            ║
║                                                                   ║
║   ┌───────────────────────────────────────────────────────┐    ║
║   │ pre-step  (còn tiếp tục không? cần append message?)      │    ║
║   └──────────────────────┬────────────────────────────────┘    ║
║                           ▼                                       ║
║   ┌───────────────────────────────────────────────────────┐    ║
║   │ STEP #1  — chuỗi Reasoning xen kẽ gọi LLM / gọi tool       │    ║
║   │                                                             │    ║
║   │   Reasoning 1 (gọi LLM)   → LLM yêu cầu tool A               │    ║
║   │   Reasoning 2 (gọi tool)  → thực thi tool A, có kết quả      │    ║
║   │   Reasoning 3 (gọi LLM)   → LLM yêu cầu tool B (kèm kết quả  │    ║
║   │                              tool A)                          │    ║
║   │   Reasoning 4 (gọi tool)  → thực thi tool B, có kết quả      │    ║
║   │   Reasoning 5 (gọi LLM)   → KHÔNG yêu cầu tool nào nữa       │    ║
║   │        ▼ (Reasoning "gọi LLM" không có tool -> Step kết thúc) │    ║
║   └───────────────────────────────────────────────────────┘    ║
║                           ▼ quay lại pre-step (mục 5)               ║
║   ┌───────────────────────────────────────────────────────┐    ║
║   │ STEP #2  — có thể chỉ 1 Reasoning (gọi LLM, không tool)    │    ║
║   │            rồi kết thúc luôn, hoặc lặp tiếp như Step #1     │    ║
║   └───────────────────────────────────────────────────────┘    ║
║                           ▼                                       ║
║                          ...  (lặp tới khi pre-step báo dừng)      ║
╚═══════════════════════════════════════════════════════════════╝
```

- **Turn**: 1 cái — trọn vòng đời xử lý 1 tin nhắn user, từ lúc nhận tới lúc trả lời xong.
- **Step**: **nhiều** cái trong 1 turn, ranh giới do **pre-step** quyết định (chạy trước mỗi
  Step). Bên trong 1 Step **không** có thêm quyết định "dừng hay tiếp" nào từ pre-step nữa —
  Step tự chạy tới khi 1 Reasoning "gọi LLM" trả lời mà không yêu cầu tool nào.
- **Reasoning**: **nhiều** cái trong 1 Step, xen kẽ 2 loại — **"gọi LLM"** (có thể yêu cầu 1
  tool) và **"gọi tool"** (thực thi đúng tool mà Reasoning "gọi LLM" ngay trước vừa yêu cầu).
  2 loại này LUÔN LÀ 2 Reasoning tách biệt, không bao giờ gộp làm 1. Sau 1 Reasoning "gọi
  tool", luôn có 1 Reasoning "gọi LLM" tiếp theo (đưa kết quả tool vào). Step chỉ kết thúc ở
  đúng 1 thời điểm: 1 Reasoning "gọi LLM" trả lời mà **không** yêu cầu tool nào.

Nói ngắn gọn: **Turn > Step > Reasoning**, quan hệ 1-nhiều ở cả 2 tầng; và trong tầng
Reasoning, **gọi LLM** và **gọi tool** luôn là 2 Reasoning riêng, nối tiếp nhau, không gộp.
Ranh giới **Step ↔ Reasoning** do nội dung Reasoning quyết định (còn tool thì Step còn tiếp),
khác với ranh giới **Turn ↔ Step** do **pre-step** quyết định.

Phần dưới đây cụ thể hoá quy ước trên thành: định nghĩa rõ ràng, sơ đồ luồng, ánh xạ sang
SSE event đã có với Frontend, state shape, cách tổ chức node LangGraph, và khoảng cách với
code hiện tại trong `core/app/agent/`.

## 1. Thuật ngữ

| Thuật ngữ | Định nghĩa | Vòng đời |
|---|---|---|
| **Turn** | Toàn bộ quá trình xử lý **1 tin nhắn** của user, từ lúc nhận request tới khi kết thúc (trả lời xong). Có thể **tạm dừng (pause)** giữa chừng khi cần hỏi user, rồi **resume** đúng chỗ đã dừng — tạm dừng không phải kết thúc turn. | Bắt đầu bằng `message.started`, kết thúc bằng `message.done`. |
| **Pre-step** | Bước quyết định *trước khi* chạy 1 Step mới — không gọi LLM/tool cho nghiệp vụ (chỉ đọc DB kiểm tra Steer đang chờ), quyết định `continue`/`answer`. **Chỉ chạy giữa 2 Step, không chạy giữa 2 Reasoning trong cùng 1 Step.** | Chạy trước mỗi Step, kể cả Step đầu tiên (và trước Step chạy lại sau khi resume). |
| **Step** | 1 chuỗi **nhiều Reasoning xen kẽ gọi LLM / gọi tool** bên trong turn, ranh giới do pre-step mở đầu và do "1 Reasoning gọi LLM không yêu cầu tool" kết thúc (mục 0). Là đơn vị nội bộ của graph — Frontend không thấy ranh giới Step, chỉ thấy chuỗi Reasoning nối tiếp nhau. | Bắt đầu khi pre-step quyết định `continue`; kết thúc khi 1 Reasoning "gọi LLM" không còn tool call → quay lại pre-step. |
| **Reasoning** | Đơn vị nhỏ nhất và cũng là đơn vị lặp — **đúng 1 hành động**: HOẶC **gọi LLM** (`stepType="default"`, có thể yêu cầu 1 tool), HOẶC **gọi tool** (`stepType="tool_call"`/`"tool_ask"`, thực thi đúng tool mà Reasoning "gọi LLM" trước đó vừa yêu cầu). | Map trực tiếp sang event `reasoning.step_started` → `reasoning.step_delta*` → `reasoning.step_completed`. |

> Lưu ý đặt tên dễ nhầm: event SSE hiện có tên `reasoning.step_*` (xem
> `async-api-doc.md` mục 2) tương ứng với khái niệm **Reasoning** ở đây (đúng 1-1: 1 Reasoning
> = 1 chuỗi `step_started → step_delta* → step_completed`), **KHÔNG** phải khái niệm **Step**
> của tài liệu này. 1 **Step** nội bộ phát ra **nhiều** event `reasoning.step_*` (nhiều
> `stepId` khác nhau) — đúng bằng số Reasoning bên trong nó (cả "gọi LLM" lẫn "gọi tool").

## 2. Sơ đồ luồng 1 turn

```
Turn bắt đầu (message.started)
        │
        ▼
┌────────────────────┐
│      Pre-step        │◀────────────────────────────────────────┐
│ (append message?      │                                          │
│  turn kết thúc chưa?)  │                                         │
└──────────┬─────────────┘                                        │
           │ quyết định                                             │
           ▼                                                        │
   ┌───────┴───────┐                                                │
   │ tiếp tục       │ kết thúc turn                                  │
   ▼                ▼                                                │
┌──────────────┐  message.delta*                                     │
│  STEP         │  message.done                                       │
│                │                                                     │
│  Reasoning:     │                                                     │
│  gọi LLM ──────┼─ yêu cầu tool? ── có ──▶ Reasoning: gọi tool ──┐      │
│      ▲          │                                                │      │
│      └──────────┼────────────────────────────────────────────────┘      │
│                 │  (kết quả tool nạp vào lần "gọi LLM" tiếp theo)         │
│                 │                                                          │
│      không có tool nào nữa ──▶ Step kết thúc ─────────────────────────────┘
│  (mỗi Reasoning: reasoning.step_started → _delta* → _completed)            │
│  (Reasoning "gọi tool" = ask_user: PAUSE tại đây, xem mục 3) ──────────────┘ chờ answer, resume đúng Reasoning này
└──────────────┘
```

- Turn chỉ kết thúc thật sự ở **1 điểm**: trả lời xong (`message.delta*` → `message.done`).
  Reasoning "gọi tool" `ask_user` **không** kết thúc turn — chỉ tạm dừng (mục 3), SSE
  connection đóng lại nhưng turn (và Step, và Reasoning đang dở) vẫn "còn sống", chờ resume.
- Turn KHÔNG có giới hạn số Step/Reasoning cứng trong thiết kế — nhưng implementation nên có
  1 `MAX_STEPS` an toàn (tránh loop vô hạn khi LLM không hội tụ) tương tự
  `AGENT_MAX_REASONING_STEPS` đã có trong `app/core/config.py` (đặt tên theo Reasoning vì đó
  mới là đơn vị lặp thật sự — xem mục 7 để đối chiếu tên biến).

## 3. "Hỏi người dùng" = 1 Reasoning kiểu "gọi tool" (`ask_user`)

Khi Agent cần hỏi thêm thông tin, đây **không** phải 1 nhánh quyết định riêng của pre-step, và
câu trả lời của user **không** phải 1 tin nhắn mới trong `messages` — coi như **1 lệnh gọi
tool bình thường** (`ask_user`) mà 1 Reasoning "gọi LLM" có thể yêu cầu, rồi Reasoning "gọi
tool" kế tiếp xử lý nó — chỉ khác tool khác ở chỗ: tool khác thực thi xong ngay trong
Reasoning "gọi tool" đó (có thể `await` khá lâu — gọi API ngoài, tra cứu... — nhưng KHÔNG cần
input từ bên ngoài graph), còn `ask_user` cần **input thật từ con người** nên Reasoning "gọi
tool" đó phải tạm dừng graph, đợi answer rồi mới hoàn tất.

`ask_user` **không phải trường hợp đặc biệt hard-code riêng** — nó là tool ĐẦU TIÊN dùng 1 cơ
chế chờ TỔNG QUÁT (`ToolSpec.requires_wait=True`, xem `app/agent/tools/base.py`) áp dụng cho
mọi tool cần tạm dừng graph chờ kết quả từ bên ngoài, kể cả tool không phải hỏi người dùng (vd
chờ 1 job async/callback bên ngoài chạy lâu). Thêm tool mới (chờ hay không chờ) chỉ cần đăng ký
1 `ToolSpec` trong `app/agent/tools/` — xem mục 5 và mục 7.

- **Publish**: Reasoning "gọi LLM" yêu cầu tool `ask_user` → publish `reasoning.step_started`/
  `_completed` bình thường (`stepType="default"`, đây vẫn chỉ là 1 lần gọi LLM). Reasoning
  "gọi tool" kế tiếp (xử lý lệnh gọi `ask_user` đó) publish `reasoning.step_started`/
  `_completed` với `stepType="tool_ask"` và `choice` (câu hỏi + options) — đúng shape đã có
  sẵn trong `fe/features/chat/types.ts` (`ReasoningStepType.tool_ask`, `ReasoningMetadata.choice`).
  Xem `async-api-doc.md` mục 2 (bảng event) và mục 3.
- **Pause/Resume**: dùng cơ chế **human-in-the-loop** có sẵn của LangGraph —
  `langgraph.types.interrupt()` ngay trong node chờ chung `tool_wait` (mục 5) khi gặp bất kỳ
  tool nào có `requires_wait=True` (`ask_user` hoặc tool khác cần đợi khá lâu/chờ callback bên
  ngoài — xem `app/agent/tools/base.py`), cần 1 **checkpointer** (lưu state graph tại điểm
  dừng) để có thể resume sau bằng `graph.invoke(Command(resume=<answer>), config)`. Dev có thể
  dùng `InMemorySaver` (đã có sẵn trong `langgraph-checkpoint`, cài kèm khi `uv add langgraph`);
  production cần checkpointer bền vững hơn tiến trình đơn (Postgres hoặc Redis — riêng Redis
  cần cài thêm gói checkpointer tương ứng, `langgraph-checkpoint-redis` **chưa có** trong deps
  hiện tại).
- **Trả lời KHÔNG qua `POST .../messages`**: `ask_user` có endpoint riêng
  (`POST /conversations/{id}/questions/{questionId}/answer`, xem `api-doc.md` mục 2.2) — Core
  nhận answer, publish "resume request" vào `agent_request_queue` (kèm đủ thông tin để tìm
  đúng checkpoint: `conversation_id` + `questionId`/`corr_id`), Agent Worker
  `Command(resume=answer)` để graph chạy tiếp **đúng Reasoning "gọi tool" đã tạm dừng** (kết
  quả tool `ask_user` chính là answer) — không phải Reasoning mới, không phải Step mới, không
  phải turn mới. Tool `requires_wait=True` khác `ask_user` có thể cần 1 kênh resume riêng
  (không nhất thiết qua endpoint này) — đây là phần tool đó tự định nghĩa, `tool_wait` chỉ lo
  phần chung (`interrupt()`/`Command(resume=...)`).
- **Tool khác (`requires_wait=False`)**: Reasoning "gọi tool" thực thi trong đúng 1 lần chạy
  node `reasoning` (có thể `await` khá lâu — gọi API ngoài, tra cứu...), publish tương tự
  (`stepType="tool_call"`), không pause; kết quả tool được đưa vào Reasoning "gọi LLM" kế tiếp
  (vẫn trong cùng Step).

## 4. State shape

```python
class ReasoningResult(BaseModel):
    """1 Reasoning — map trực tiếp sang reasoning.step_started/_delta/_completed.
    LUÔN LÀ 1 TRONG 2 LOẠI: "gọi LLM" (step_type="default") HOẶC "gọi tool"
    (step_type="tool_call"/"tool_ask") — không bao giờ cả 2 trong 1 ReasoningResult."""
    step_id: str
    title: str
    content: str
    step_type: Literal["default", "tool_call", "tool_ask"] = "default"
    choice: MessageChoice | None = None  # chỉ có khi tool hiển thị dạng hỏi-chọn (vd ask_user)
    step_continues: bool  # false CHỈ khi đây là Reasoning "gọi LLM" không yêu cầu tool nào

class StepResult(BaseModel):
    """1 Step đã đóng = danh sách Reasoning liên tiếp (xen kẽ gọi LLM / gọi tool)."""
    reasoning: list[ReasoningResult]

class PendingTool(BaseModel):
    """Trạng thái chờ TỔNG QUÁT cho MỌI tool `requires_wait=True` — không hard-code
    riêng cho `ask_user`. `payload` gửi nguyên vẹn cho `interrupt()`; node `tool_wait`
    tra `tool_name` trong registry (`app/agent/tools.TOOLS_BY_NAME`) để biết cách xử
    lý resume."""
    tool_call_id: str
    tool_name: str
    payload: dict

class TurnState(TypedDict):
    conversation_id: str
    messages: Annotated[list[AnyMessage], add_messages]   # context tích luỹ qua các Reasoning
    steps: list[StepResult]                                 # các Step đã hoàn tất
    current_step: list[ReasoningResult]                     # Reasoning của Step đang chạy dở
    step_count: int                                          # đếm theo Reasoning, không phải Step
    outcome: Literal["continue", "answer"] | None            # kết quả pre_step gần nhất
    final_answer: str | None
    pending_tool: PendingTool | None    # tool requires_wait=True đang chờ interrupt() resume
```

- `current_step` tích luỹ dần qua từng Reasoning (cả 2 loại); khi 1 Reasoning "gọi LLM"
  không yêu cầu tool (`step_continues=False`), `current_step` được đóng lại thành 1
  `StepResult` mới trong `steps`, rồi quay lại `pre_step`.
- `outcome` chỉ 2 giá trị — driver cho conditional edge trong graph (mục 5). "Tạm dừng chờ
  hỏi" **không** nằm trong `outcome`: đó là hiệu ứng của `interrupt()` trong node `tool_wait`
  (mục 3), LangGraph tự quản lý qua checkpointer.
- `pending_tool` generic hoá `pending_question`/`pending_tool_call_id` của bản trước (từng
  hard-code riêng cho `ask_user`) — bất kỳ tool `requires_wait=True` nào cũng dùng chung field
  này, `tool_name` cho biết tra `ToolSpec` nào để xử lý resume.

## 5. Tổ chức node LangGraph (thực tế trong `app/agent/graph.py`)

Graph có **4 node**: `pre_step`, `reasoning`, `tool_wait`, `finalize`. `reasoning` tự lặp và tự
phân biệt 2 loại Reasoning bằng nội dung message cuối cùng — **không cần 2 node riêng cho "gọi
LLM" và "gọi tool"**, quyết định bằng: message cuối là `AIMessage` có `tool_calls` chưa thực
thi → làm Reasoning "gọi tool"; ngược lại → làm Reasoning "gọi LLM". Tool nào `requires_wait`
cần **node phụ `tool_wait`** — lý do ở dưới. `reasoning` tra tool theo tên trong registry
(`app/agent/tools.TOOLS_BY_NAME`) — KHÔNG hard-code tên tool cụ thể nào; thêm tool mới chỉ cần
đăng ký 1 `ToolSpec` (`app/agent/tools/`, xem mục 7), không cần sửa node.

```
START → pre_step ──(outcome=continue)──→ reasoning ──┐
           ▲                                  │        │ còn việc (vừa "gọi LLM" ra tool_call,
           │                                  │◀───────┘  hoặc vừa "gọi tool" [requires_wait=
           │                                  │           False] xong) → lặp lại reasoning
           │                                  │           (VẪN trong cùng Step)
           │                                  │
           │                                  │ tool_call là tool `requires_wait=True`
           │                                  ▼
           │                             tool_wait ──interrupt()──▶ (chờ resume) ──▶ reasoning
           │            "gọi LLM" không yêu cầu tool nào nữa → Step kết thúc
           └──────────────────────────────────┘
           │
           └──(outcome=answer)────→ finalize → END
```

- **`pre_step`**: KHÔNG gọi LLM/tool nghiệp vụ. Có thể:
  - Rule thuần (vd: `step_count >= MAX_STEPS` → `outcome=answer` bắt buộc), và/hoặc
  - Đọc `MessageRepository.list_pending_steers` — nếu có Steer đang chờ, append vào
    `messages` trước khi sang `reasoning`.
- **`reasoning`**: nhận biết đang cần làm Reasoning loại nào bằng cách nhìn message cuối
  cùng trong `messages` (hàm `_pending_tool_call()`):
  - Message cuối là `AIMessage` có `tool_calls` (chưa có `ToolMessage` tương ứng) → làm
    Reasoning **"gọi tool"** (`_run_tool()`): tra `ToolSpec` theo tên trong
    `TOOLS_BY_NAME` (`app/agent/tools/`) — KHÔNG hard-code tên tool nào. Tool
    `requires_wait=True` (`ask_user`, hoặc tool khác cần chờ lâu/callback ngoài): gọi
    `spec.build_wait_request()` build payload, lưu vào `pending_tool` (generic, không riêng
    `ask_user`) rồi **route sang `tool_wait`** (KHÔNG tự `interrupt()` ngay trong `reasoning`
    — xem lý do bên dưới); tool `requires_wait=False` gọi `await spec.run()` (có thể chạy
    lâu), publish `stepType="tool_call"`, lặp lại `reasoning`.
  - Ngược lại → làm Reasoning **"gọi LLM"** (`_run_llm()`): gọi
    `get_llm_with_tools(ALL_TOOLS)` (toàn bộ tool trong registry), publish
    `stepType="default"`. Có `tool_calls` → lặp lại `reasoning` (Reasoning kế tiếp sẽ là
    "gọi tool"); không có → Step đóng, quay lại `pre_step`.
  - Cả 2 nhánh đều publish `reasoning.step_started/_delta/_completed` cho Reasoning vừa chạy.
- **`tool_wait`**: node chờ TỔNG QUÁT cho mọi tool `requires_wait=True` — **chỉ** làm 1 việc
  — `interrupt(pending_tool.payload)` — rồi tra `ToolSpec.on_resume()` (theo
  `pending_tool.tool_name`) để build `ToolMessage` từ answer + (nếu có) cập nhật
  `choice.answered`, quay lại `reasoning`. Vì sao tách riêng khỏi `reasoning` thay vì gọi
  `interrupt()` ngay trong `_run_tool()`: LangGraph **re-run lại từ đầu node** khi resume —
  nếu `interrupt()` nằm giữa `_run_tool()` (sau đoạn build payload), resume sẽ chạy lại đoạn
  build đó lần nữa (vô hại nhưng thừa); tách thành node riêng có `interrupt()` là **câu lệnh
  đầu tiên** đảm bảo resume không làm lại việc gì thừa. Đây vẫn tính là **cùng 1 Reasoning
  "gọi tool"** về mặt khái niệm (chỉ 1 `ReasoningResult` được tạo, trong `_run_tool()`) —
  `tool_wait` chỉ là chi tiết cài đặt để pause/resume an toàn, không tạo Reasoning mới.
- **`finalize`**: build câu trả lời cuối từ `messages`/`steps`, set `final_answer`, đây là nơi
  publish `message.delta*` + `message.done`.

## 6. Điều kiện dừng / tạm dừng turn

1. **Trả lời xong** (`outcome=answer`): đủ thông tin, Reasoning "gọi LLM" chốt câu trả lời
   (không yêu cầu tool) → `finalize` → turn **kết thúc thật sự**.
2. **Chạm giới hạn an toàn** (`step_count >= MAX_STEPS`): `pre_step` ép `outcome=answer` dù
   model chưa tự chốt, dùng nội dung Reasoning gần nhất làm câu trả lời tạm (tương tự
   `finalize()` hiện tại trong `app/agent/graph.py`) → turn **kết thúc thật sự**.
3. **Tạm dừng chờ** (Reasoning "gọi tool" gặp tool `requires_wait=True`, mục 3): turn **chưa
   kết thúc** — `interrupt()` (node `tool_wait`), chờ resume tương ứng tool đó — với
   `ask_user` là `POST .../questions/{questionId}/answer` (`api-doc.md` mục 2.2) — để
   `Command(resume=...)` chạy tiếp đúng Reasoning đã dừng.

Lưu ý: **không có** khái niệm "Step chạm giới hạn rồi tự dừng" tách riêng — 1 Step tự nhiên
kết thúc khi Reasoning "gọi LLM" không yêu cầu tool (mục 0); `MAX_STEPS` ở đây là giới hạn an
toàn cấp **Reasoning** (tổng số Reasoning toàn turn — cả "gọi LLM" lẫn "gọi tool" — không
phải số Step), phòng khi LLM cứ gọi tool liên tục không dừng trong 1 Step duy nhất.

## 7. Trạng thái implement (`core/app/agent/`)

✅ **Đã implement đúng theo tài liệu này**: `state.py` (`TurnState`/`StepResult`/
`ReasoningResult`/`PendingTool`, field `step_continues` — **không** phải `has_tool_call` như 1
bản draft trước, tên cũ dễ khiến hiểu nhầm là 1 Reasoning gộp cả gọi-LLM-và-gọi-tool),
`graph.py` — 4 node `pre_step`/`reasoning`/`tool_wait`/`finalize` (mục 5), node `reasoning` tự
phân biệt 2 loại Reasoning bằng hàm `_pending_tool_call()` (nhìn message cuối cùng), tách 2 hàm
nội bộ `_run_llm()`/`_run_tool()` — mỗi hàm tạo **đúng 1** `ReasoningResult`, `interrupt()`
(trong `tool_wait`, TỔNG QUÁT cho mọi tool `requires_wait=True`) + `InMemorySaver`. `worker.py`
publish đủ event catalog cho từng Reasoning (dù là gọi LLM hay gọi tool) + xử lý cả turn mới
lẫn resume.

**Tool nghiệp vụ — `app/agent/tools/` (package, không còn là 1 file `tools.py`)**: điểm mở
rộng duy nhất khi thêm tool mới, tách theo hợp đồng `ToolSpec` (mục 3/4):

| File | Vai trò |
|---|---|
| `base.py` | Hợp đồng `ToolSpec`/`ToolWaitRequest`/`ToolResumeResult` — `graph.py` chỉ import từ đây, không biết tool cụ thể nào. |
| `ask_user.py` | Tool đầu tiên, ví dụ mẫu cho tool `requires_wait=True` (build câu hỏi, xử lý resume thành `AnsweredChoiceDto`). |
| `__init__.py` | Registry: `TOOL_SPECS` (danh sách đăng ký), `TOOLS_BY_NAME` (tra theo tên, dùng trong `graph.py`), `ALL_TOOLS` (bind vào LLM, `app/agent/llm.py`). |

Thêm 1 tool nghiệp vụ thật (không cần chờ, chỉ chạy lâu): viết module con định nghĩa `ToolSpec`
với `run()` (`async def run(tool_call) -> str`, cứ `await` bình thường dù chạy lâu), thêm vào
`TOOL_SPECS` — không sửa `graph.py`/`state.py`. Thêm 1 tool cần chờ callback ngoài (không phải
hỏi người dùng): tương tự nhưng `requires_wait=True` + `build_wait_request()`/`on_resume()` —
tự quyết định payload `interrupt()` và cách map answer về `ToolMessage` (không bắt buộc phải có
`choice`/`questionId` kiểu `ask_user` — đó là chi tiết riêng của `ask_user`, không phải phần
chung của `PendingTool`).

Giới hạn đã biết (ghi trong code, không giấu): giả định LLM chỉ gọi **tối đa 1 tool mỗi lần
"gọi LLM"** (ép qua system prompt) — chưa xử lý model gọi nhiều tool song song trong cùng 1
response. Tool `requires_wait=True` khác `ask_user` vẫn cần tự thêm kênh resume riêng (endpoint
API hoặc cơ chế khác) nếu không đi qua `POST .../questions/{questionId}/answer` — `tool_wait`
chỉ lo phần chung (`interrupt()`), không tự phát sinh endpoint mới.

Sai khác nhỏ khác so với mô tả gốc (mục 3/6), ghi nhận để không nhầm khi đọc code:

| Hạng mục | Mô tả gốc | Thực tế trong code |
|---|---|---|
| Checkpointer | Gợi ý Postgres/Redis cho production | `InMemorySaver` cố định — cần tự đổi khi deploy nhiều Agent Worker instance |
| `message_id` (turn) | "Agent Worker sinh" | **Core sinh** lúc publish turn (`MessageService`), Agent Worker chỉ tái dùng — cần thiết để Core set được Redis "active turn" key trước khi Agent Worker chạy |

✅ Đã khớp mô tả gốc (không còn là "sai khác"): persist khi pause/done relay qua
`agent_response_queue` để Core ghi DB (`app/agent/response_consumer.py`) — xem
`async-api-doc.md` đầu file.

Việc còn lại: tool nghiệp vụ thật (ngoài `ask_user`), `sources`, Celery hoá worker — xem
`async-api-doc.md` mục 7.
