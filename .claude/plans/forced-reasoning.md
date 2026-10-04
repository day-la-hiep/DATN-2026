# Ép agent lập luận — reasoning có cấu trúc + cổng kiểm soát bằng middleware

## Trạng thái triển khai

Đã làm và đã chạy thử với model thật (`AGENT_MODEL` trong `.env`): `record_reasoning`
(`agent/tools/reasoning.py`), middleware `force_reasoning` + `enforce_initial_reasoning`
(`agent/middleware/model.py`), step theo `stage` (`agent/middleware/tool.py`), cập nhật prompt.
`make_plan` (`agent/tools/plan.py`) đã xóa.

Khác thiết kế bên dưới:
- **Không có state riêng** (`reasoning_log`, `evidence_since_reasoning`, `reasoning_retries`): trạng thái
  suy ra từ `messages` của turn (`analyze_turn`) nên tự đúng qua checkpoint và `ask_user` resume.
- **Cơ chế ép đổi từ `after_model` sang `wrap_model_call`** (`force_reasoning`): `turn.py` stream token
  ra `message.delta` ngay khi model sinh, nên chặn câu trả lời bằng `after_model` sẽ để bản nháp bị từ
  chối lọt ra người dùng. Thay vào đó, sau mỗi đợt `ToolMessage` chưa được lập luận, request được ghi đè
  bằng `tool_choice=record_reasoning` + chỉ bind tool đó — ép TRƯỚC khi sinh chữ.
- `enforce_initial_reasoning` (`after_model`) là lưới an toàn: (R1) gọi tool tra cứu khi chưa lập luận ->
  `RemoveMessage` + feedback (không có chữ nào lọt ra); (R3) phản hồi rỗng -> làm lại. Đã thấy provider
  đôi khi bỏ qua `tool_choice`, nên lưới này cần thiết. Tối đa `MAX_REASONING_RETRIES` lần rồi cho qua.
- Đếm lập luận không hợp lệ theo THAM SỐ tool call (lỗi schema bị `ToolNode` bắt trước khi tool chạy,
  nội dung `ToolMessage` không có tiền tố của tool).
- Schema chịu sai kiểu nhẹ của model (`missing` là chuỗi, `red_flags` là list) thay vì từ chối.
- Chưa làm: bật lại `critic_review` và đối chiếu câu trả lời với bản `final` (mục 4) — critic vẫn đang
  comment trong `default_middleware()`; chưa làm liên kết với `generate_differential` (mục 5).
- FE không cần sửa: mỗi `stage` có tên hiển thị riêng nên dedupe theo tên ở `store.ts` không ghi đè nhau.
- Giới hạn còn lại: lượt medical mà model trả lời thẳng không gọi tool nào thì không bị ép (không phân
  biệt được với chào hỏi mà không đọc nội dung).

## Cập nhật: gộp `next_best_question` vào `record_reasoning`

Không còn tool `next_best_question`. Khi `record_reasoning` có `next_action="ask_user"` và từ 2 giả
thuyết trở lên, nó gọi `suggest_discriminating_questions` (`agent/tools/differential.py`) và kèm
"Gợi ý câu hỏi phân biệt" vào kết quả; agent đọc rồi mới `ask_user`. Tham số tuỳ chọn
`known_phenotype_ids` để không gợi ý lại phenotype đã biết. Lỗi Neo4j khi gợi ý không làm hỏng lập luận.

## Context

Hiện tại "lập luận" của agent chỉ được **nhờ** qua system prompt (`agent/prompt/orchestrator.py`
mục 3, 6, 8), không có gì bắt buộc:

- `make_plan` (`agent/tools/plan.py`) là tool echo — model có thể bỏ qua hoặc điền qua loa
  (`reasoning` là chuỗi tự do). Không có gì kiểm tra nó được gọi đầu tiên.
- Mục 8 "Tự kiểm trước khi trả lời" chỉ là checklist trong prompt; model không phải xuất ra
  kết quả tự kiểm.
- `critic_review` (`agent/middleware/model.py`) **đang bị comment** trong `default_middleware()`
  (`agent/graph/chat_graph.py`), và critic chỉ thấy văn bản tự do nên khó chấm "đã lập luận chưa".
- Model hiện dùng trả `content=''` mỗi khi gọi tool (ghi trong `plan.py`), nên lập luận chỉ quan sát
  được qua **tham số tool call** — đó là kênh đáng tin duy nhất.

Nguyên tắc: **đừng dựa vào lời nhắc, dựa vào schema + cổng**. Biến lập luận thành tool call có schema
chặt, lưu vào state, và chặn câu trả lời cuối nếu thiếu.

## Thiết kế

### 1. Thay `make_plan` bằng tool lập luận có cấu trúc `record_reasoning`

Schema (Pydantic, `args_schema`):

```
record_reasoning(
  stage: "initial" | "after_evidence" | "final",
  observations: list[{fact, source: "user"|"tool:<name>"|"image"|"web:<domain>"}],   # dữ kiện, có nguồn
  hypotheses: list[{
      disease, 
      supports: list[str],        # dữ kiện (trong observations) ủng hộ
      contradicts: list[str],     # dữ kiện mâu thuẫn
      missing: list[str],         # còn thiếu để xác nhận/loại trừ
      confidence: "cao"|"vừa"|"thấp",
  }],                             # 2–4 phần tử
  red_flags: {checked: list[str], present: list[str]},
  next_action: "call_tool" | "ask_user" | "answer",
  next_action_reason: str,
)
```

- Tool không tra cứu gì; validate (số hypotheses 2–4, mỗi hypothesis có ít nhất `supports` hoặc
  `contradicts`, `supports`/`contradicts` phải tham chiếu tới `observations`) rồi lưu vào state
  `reasoning_log` và echo bản tóm tắt.
- Trả lỗi validate dạng `ToolMessage` để model tự sửa (giữ nguyên cách `emit_tool_result` xử lý lỗi).
- FE vẫn thấy qua `message.thinking`/`tool_call` (thêm nhãn vào `TOOL_DISPLAY_NAMES`).

### 2. Mở rộng state

`CriticState` (`agent/graph/common.py`) đổi/tách thành `ReasoningState` có:
`reasoning_log: list[dict]`, `evidence_since_reasoning: int` (số `ToolMessage` kể từ lần
`record_reasoning` gần nhất), `reasoning_retries: int`. Không dùng reducer cộng dồn; ghi đè như
`critic_retries` hiện tại.

### 3. Cổng bắt buộc (middleware `enforce_reasoning`, `@after_model(can_jump_to=["model"])`)

Chạy sau mỗi lần model trả lời, ba luật (vi phạm → chèn `HumanMessage` hệ thống + `jump_to="model"`,
giới hạn `MAX_REASONING_RETRIES=2`/turn, hết thì cho qua để không treo turn):

| Luật | Điều kiện vi phạm | Feedback |
|---|---|---|
| R1 — lập kế hoạch trước | lượt có nội dung y khoa mà tool call đầu tiên không phải `record_reasoning(stage="initial")` | "Gọi record_reasoning(initial) trước" |
| R2 — lập luận sau bằng chứng | model định gọi tool tiếp/hoặc trả lời cuối trong khi `evidence_since_reasoning >= 1` chưa có `record_reasoning(after_evidence)` | "Cập nhật giả thuyết sau kết quả tool" |
| R3 — không trả lời khi chưa `final` | câu trả lời cuối (AIMessage không `tool_calls`) mà `reasoning_log` chưa có `stage="final"` với `next_action="answer"`, hoặc `red_flags.checked` rỗng | "Gọi record_reasoning(final) rồi mới trả lời" |

Phân biệt "lượt có nội dung y khoa" giống `critic_review`: có `ToolMessage` hoặc `HumanMessage` chứa
ảnh/triệu chứng; chào hỏi/ngoài phạm vi (prompt mục 2) bỏ qua để không tốn lượt.

### 4. Ràng buộc câu trả lời với lập luận đã ghi

Bật lại `critic_review` và đưa `reasoning_log[-1]` vào input của critic. Thêm luật vào
`prompt/critic.py`:

- Thứ tự/độ tin cậy trong câu trả lời phải khớp `hypotheses` của bản `final`.
- Không nhắc bệnh nào không có trong `hypotheses`.
- `red_flags.present` không rỗng mà không khuyên khám ngay → từ chối.
- Có `next_action="ask_user"` trong log nhưng lại trả lời chốt, hoặc ngược lại → từ chối.

Cân nhắc rút ngắn: R1–R3 xử lý *có lập luận hay không*, critic xử lý *lập luận có được tôn trọng không*.

### 5. Để lập luận dựa trên tính toán thay vì đoán

Kết hợp với `diagnostic-tools-expansion.md`: `generate_differential` trả bảng xếp hạng có
`matched`/`missing_common`; `next_best_question` trả phenotype phân biệt. `record_reasoning`
cho phép (tùy chọn) trường `from_tool_ranking` để đối chiếu — nếu `hypotheses` lệch hẳn top-N của
`generate_differential` mà không giải thích trong `next_action_reason`, R2 coi là vi phạm. Đây là bước
sau, không chặn phần 1–4.

### 6. Hiển thị (đã chốt)

- **Quá trình lập luận hiển thị dạng TEXT ở các step**, không hiện JSON thô. Mỗi lần gọi
  `record_reasoning`, `emit_tool_result` (`agent/middleware/tool.py`) render args thành đoạn văn
  tiếng Việt ngắn (`render_reasoning_text`): dữ kiện đã có → các giả thuyết kèm lý do ủng hộ/mâu
  thuẫn và độ tin cậy → điều còn thiếu/cờ đỏ → bước tiếp theo. Text này đi vào `content` của step
  `type="tool_call"` (title theo `stage`: "Lập luận ban đầu" / "Cập nhật sau bằng chứng" / "Kết luận
  lập luận"), cũng được lưu vào `reasoning_steps` → persist ở `Message.extra.reasoning` nên tải lại
  hội thoại vẫn thấy.
- `step_id` khóa theo `stage` (không dedup ghi đè giữa các stage) để 3 bước không đè nhau.
- **Người dùng cuối chỉ thấy câu trả lời cuối** (mục 9 prompt) ở khung tin nhắn chính; các step là
  phần thu gọn/xem thêm. Câu trả lời cuối không lặp lại nguyên bảng giả thuyết, chỉ tóm tắt theo
  cấu trúc 4 phần hiện có.

### 7. Prompt

Sửa `orchestrator.py`: thay bước 0 (`make_plan`) và mục 8 bằng mô tả ngắn `record_reasoning` ba stage;
bỏ checklist mục 8 (đã chuyển thành schema). Giữ prompt ngắn — ép buộc nằm ở middleware, không ở lời văn.

### 8. Tích hợp `search_trusted_web` / `fetch_trusted_page`

Khi `observations` có `source="web:<domain>"`, critic kiểm tra: (a) domain nằm trong allowlist,
(b) khẳng định y khoa dựa trên web có trích domain trong câu trả lời, (c) nếu web mâu thuẫn guideline
BYT/WHO thì câu trả lời nêu rõ và ưu tiên guideline. Chi tiết tool ở `diagnostic-tools-expansion.md` mục F.

## Thay đổi file

| File | Việc |
|---|---|
| `agent/tools/reasoning.py` (mới) | `record_reasoning`, schema, validate; ghi vào state (dùng `Command(update=...)`) |
| `agent/tools/plan.py` | giữ tạm để tương thích, xóa sau khi chuyển hẳn |
| `agent/graph/common.py` | `ReasoningState`, hằng số `MAX_REASONING_RETRIES`, nhãn `TOOL_DISPLAY_NAMES` |
| `agent/middleware/tool.py` | render text cho `record_reasoning`, `step_id` theo `stage` |
| `agent/middleware/model.py` | `enforce_reasoning`; bật `critic_review`, truyền `reasoning_log` |
| `agent/prompt/orchestrator.py`, `critic.py` | cập nhật như mục 4, 6 |
| `agent/graph/chat_graph.py` | `ALL_TOOLS`, `default_middleware()` (thứ tự: `enforce_reasoning` trước `critic_review`) |

## Rủi ro / đánh đổi

- **Chi phí và độ trễ:** thêm 2–3 lượt gọi model mỗi ca (initial, after_evidence, final) + critic.
  Giảm bằng cách cho phép gộp `after_evidence` và `final` khi chỉ có 1 vòng tra cứu.
- **Model yếu điền cho có** (hypotheses bịa, `supports` không có thật): validate tham chiếu
  `observations`, và critic đối chiếu với `ToolMessage`. Không loại bỏ hoàn toàn được.
- **Vòng lặp retry:** giới hạn cứng `MAX_REASONING_RETRIES`, hết thì cho qua và ghi log để review.
- **`content=''` khi gọi tool:** không ảnh hưởng vì mọi lập luận nằm trong tham số tool.
- **Tương thích FE:** `record_reasoning` xuất hiện như 1 bước `tool_call`; dedup theo tên hiển thị
  của `emit_tool_result` sẽ ghi đè lần gọi trước — cần khóa theo `stage` (xem `step_id` trong
  `agent/middleware/tool.py`).

## Câu hỏi mở

1. Ngân sách tool (~8 lần/lượt trong prompt) có tính `record_reasoning` không? Đề xuất: không tính.
2. Dùng critic là LLM cùng model (như hiện tại) hay model mạnh hơn cho bước kiểm duyệt?

## Kiểm thử

- Unit: validate schema (thiếu `supports`, tham chiếu observation không tồn tại, 1 hypothesis).
- Middleware: mô phỏng chuỗi message vi phạm R1/R2/R3 → đúng feedback; hết retry → cho qua.
- Kịch bản end-to-end: (a) chào hỏi — không bị ép; (b) triệu chứng đủ thông tin; (c) triệu chứng thiếu
  → `ask_user`; (d) có cờ đỏ → khuyên khám ngay.
- So sánh trước/sau trên bộ ca mẫu: tỉ lệ có `record_reasoning`, độ lệch giữa `final` và câu trả lời,
  số lượt gọi model trung bình.
- `uv run pyright` sạch cho file mới.
