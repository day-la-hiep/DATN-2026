"""Tool `record_reasoning` — ép agent lập luận CÓ CẤU TRÚC, quan sát được qua step.

Thay `make_plan` (chuỗi tự do, không ai kiểm tra). Model hiện dùng trả `content=''` mỗi khi gọi
tool, nên lập luận chỉ hiển thị được nếu là THAM SỐ của 1 tool call; tool này validate tham số
theo schema, render thành đoạn văn tiếng Việt (nội dung step `tool_call` mà FE hiển thị, xem
`middleware/tool.py::emit_tool_result`) và không tra cứu gì.

Cơ chế ép nằm ở `middleware/model.py` (`force_reasoning`, `enforce_initial_reasoning`): trạng thái
lập luận được SUY RA từ chính `messages` của turn (các lần gọi `record_reasoning` + `ToolMessage`),
không lưu state riêng — nên tự đúng qua checkpoint/resume (`ask_user`).

3 giai đoạn (`stage`):
  - initial        : trước khi gọi tool tra cứu đầu tiên — dữ kiện đã biết + giả thuyết ban đầu.
  - after_evidence : ngay sau 1 đợt kết quả tool — cập nhật giả thuyết theo bằng chứng mới.
  - final          : đủ căn cứ để trả lời/hỏi — kết luận xếp hạng, cờ đỏ đã kiểm tra.
"""
from typing import Any, Literal

from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError, field_validator

TOOL_NAME = "record_reasoning"
INVALID_PREFIX = "Không hợp lệ:"
# Tin nhắn nội bộ chèn bởi middleware — KHÔNG phải lời người dùng, không tính là ranh giới turn.
FEEDBACK_PREFIX = "[Hệ thống kiểm soát lập luận — không phải lời người dùng]"
_SYSTEM_MARKERS = (FEEDBACK_PREFIX, "[Hệ thống kiểm duyệt")

# Tool KHÔNG cung cấp bằng chứng chẩn đoán -> không kích hoạt yêu cầu lập luận.
_NON_EVIDENCE_TOOLS = {TOOL_NAME, "save_memory"}

STAGE_LABELS = {
    "initial": "Lập luận ban đầu",
    "after_evidence": "Cập nhật lập luận sau bằng chứng",
    "final": "Kết luận lập luận",
}

Stage = Literal["initial", "after_evidence", "final"]


class Observation(BaseModel):
    fact: str = Field(description="1 dữ kiện ngắn gọn (lời người dùng, kết quả tool, ảnh, web)")
    source: str = Field(
        description='Nguồn: "user", "image", "tool:<tên tool>" hoặc "web:<domain>"'
    )


def _as_list(value: Any) -> Any:
    """Model hay trả 1 chuỗi/1 số thay vì list — bọc lại thay vì từ chối cả lần lập luận."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class Hypothesis(BaseModel):
    disease: str = Field(description="Tên bệnh/giả thuyết")
    supports: list[int] = Field(
        default_factory=list,
        description="Số thứ tự (bắt đầu từ 1) của các dữ kiện trong `observations` ỦNG HỘ",
    )
    contradicts: list[int] = Field(
        default_factory=list,
        description="Số thứ tự các dữ kiện trong `observations` MÂU THUẪN với giả thuyết",
    )
    missing: list[str] = Field(
        default_factory=list, description="Còn thiếu gì để xác nhận hoặc loại trừ"
    )
    confidence: Literal["cao", "vừa", "thấp"]

    _coerce = field_validator("supports", "contradicts", "missing", mode="before")(_as_list)


class RedFlags(BaseModel):
    checked: list[str] = Field(
        default_factory=list, description="Các cờ đỏ đã kiểm tra (đã hỏi hoặc đã có thông tin)"
    )
    present: list[str] = Field(default_factory=list, description="Cờ đỏ ĐANG có ở người bệnh")

    _coerce = field_validator("checked", "present", mode="before")(_as_list)


def _first_red_flags(value: Any) -> Any:
    """Model đôi khi trả `red_flags` là list 1 phần tử."""
    if isinstance(value, list):
        return value[0] if value else {}
    return value


class ReasoningInput(BaseModel):
    stage: Stage = Field(
        description="initial: trước tra cứu đầu tiên; after_evidence: sau kết quả tool; "
        "final: đủ căn cứ để trả lời hoặc hỏi người dùng"
    )
    observations: list[Observation] = Field(
        min_length=1, description="Dữ kiện đã biết, mỗi dữ kiện kèm nguồn"
    )
    hypotheses: list[Hypothesis] = Field(
        min_length=1, max_length=4, description="1-4 giả thuyết xếp theo mức phù hợp giảm dần"
    )
    red_flags: RedFlags = Field(default_factory=RedFlags)
    next_action: Literal["call_tool", "ask_user", "answer"]
    next_action_reason: str = Field(description="1-2 câu: vì sao chọn bước tiếp theo này")
    known_phenotype_ids: list[str] = Field(
        default_factory=list,
        description="(Tuỳ chọn) `primekg_id` phenotype đã biết/đã hỏi — dùng khi "
        'next_action="ask_user" để gợi ý câu hỏi phân biệt không lặp lại',
    )

    _coerce_flags = field_validator("red_flags", mode="before")(_first_red_flags)
    _coerce_known = field_validator("known_phenotype_ids", mode="before")(_as_list)


def validate_reasoning(args: dict[str, Any]) -> tuple[ReasoningInput | None, list[str]]:
    """Kiểm tra schema + ràng buộc ngữ nghĩa. Trả `(input, [])` nếu hợp lệ, ngược lại
    `(None, [lỗi...])`."""
    try:
        data = ReasoningInput.model_validate(args)
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]

    problems: list[str] = []
    n = len(data.observations)
    for i, h in enumerate(data.hypotheses, 1):
        bad = [x for x in [*h.supports, *h.contradicts] if not 1 <= x <= n]
        if bad:
            problems.append(
                f"Giả thuyết {i} ({h.disease}) tham chiếu dữ kiện không tồn tại: {bad} "
                f"(chỉ có 1..{n})."
            )
        if not (h.supports or h.contradicts or h.missing):
            problems.append(
                f"Giả thuyết {i} ({h.disease}) không có dữ kiện ủng hộ/mâu thuẫn hay điều còn "
                "thiếu — chỉ nêu giả thuyết có căn cứ."
            )
    if data.stage != "initial" and not data.red_flags.checked:
        problems.append("`red_flags.checked` rỗng — phải nêu các cờ đỏ đã kiểm tra.")
    if data.stage == "final" and data.next_action == "call_tool":
        problems.append('stage "final" không đi kèm next_action "call_tool".')
    return (None, problems) if problems else (data, [])


def _refs(indexes: list[int]) -> str:
    return ", ".join(f"[{i}]" for i in indexes) if indexes else "—"


_ACTION_LABELS = {
    "call_tool": "tra cứu thêm",
    "ask_user": "hỏi người dùng",
    "answer": "trả lời",
}


def render_reasoning(data: ReasoningInput) -> str:
    """Đoạn văn hiển thị ở step (Markdown nhẹ, tiếng Việt) — người dùng đọc được, không lộ JSON."""
    lines = [f"**{STAGE_LABELS[data.stage]}**", "", "Dữ kiện đã có:"]
    lines += [f"[{i}] {o.fact} (nguồn: {o.source})" for i, o in enumerate(data.observations, 1)]
    lines += ["", "Các giả thuyết:"]
    for i, h in enumerate(data.hypotheses, 1):
        lines.append(f"{i}. {h.disease} — độ tin cậy {h.confidence}")
        lines.append(f"   Ủng hộ: {_refs(h.supports)} · Mâu thuẫn: {_refs(h.contradicts)}")
        if h.missing:
            lines.append(f"   Còn thiếu: {'; '.join(h.missing)}")
    rf = data.red_flags
    lines += [
        "",
        f"Cờ đỏ đã kiểm tra: {'; '.join(rf.checked) or 'chưa'}"
        + (f" · ĐANG CÓ: {'; '.join(rf.present)}" if rf.present else ""),
        f"Bước tiếp theo: {_ACTION_LABELS[data.next_action]} — {data.next_action_reason}",
    ]
    return "\n".join(lines)


def _render_questions(result: dict[str, Any]) -> str:
    questions = result.get("questions") or []
    if not questions:
        return ""
    lines = ["", "Gợi ý câu hỏi phân biệt (từ đồ thị, chỉ để tham khảo):"]
    for q in questions:
        lines.append(
            f"- {q['phenotype']}: có ở {', '.join(q['present_in'])}; "
            f"không có ở {', '.join(q['absent_in'])}"
        )
    return "\n".join(lines)


@tool(args_schema=ReasoningInput)
async def record_reasoning(**kwargs: Any) -> str:
    """Ghi lại LẬP LUẬN có cấu trúc — không tra cứu bệnh/bằng chứng, chỉ buộc bạn nêu dữ kiện,
    giả thuyết và bước tiếp theo để người dùng thấy được quá trình suy luận. Gọi ĐÚNG lúc:
    (1) stage="initial": TRƯỚC tool tra cứu đầu tiên của lượt có nội dung y khoa;
    (2) stage="after_evidence": ngay sau mỗi đợt kết quả tool (hệ thống sẽ yêu cầu);
    (3) stage="final": khi đủ căn cứ để trả lời hoặc hỏi người dùng.
    Mỗi giả thuyết phải dựa trên dữ kiện đã liệt kê (tham chiếu theo số thứ tự); chỉ dùng dữ
    kiện thật từ người dùng/kết quả tool, không bịa. Kiến thức nền không phải dữ kiện.

    Khi next_action="ask_user" và có từ 2 giả thuyết trở lên, kết quả kèm GỢI Ý CÂU HỎI PHÂN
    BIỆT (phenotype chia đôi tốt nhất các giả thuyết, tính từ đồ thị). Khi đó hãy gọi
    `record_reasoning` MỘT MÌNH, đọc gợi ý trong kết quả rồi mới `ask_user`; tự diễn đạt gợi ý
    thành 1 câu hỏi tiếng Việt dễ hiểu, và chỉ dùng nếu người dùng có thể tự trả lời được."""
    data, problems = validate_reasoning(kwargs)
    if data is None:
        return f"{INVALID_PREFIX} " + " | ".join(problems) + " — hãy gọi lại với nội dung đúng."
    text = render_reasoning(data)
    if data.next_action == "ask_user" and len(data.hypotheses) >= 2:
        try:
            # Import trễ: `differential` kéo Neo4j/Qdrant/embedding — không cần khi chỉ phân tích.
            from agent.tools.differential import suggest_discriminating_questions

            result = await suggest_discriminating_questions(
                [h.disease for h in data.hypotheses], data.known_phenotype_ids
            )
            text += _render_questions(result)
        except Exception as exc:  # noqa: BLE001 — gợi ý là phần thêm, không làm hỏng lập luận
            print(f"[record_reasoning] gợi ý câu hỏi lỗi: {exc}")
    return text


# ---------------------------------------------------------------------------
# Phân tích trạng thái lập luận của turn hiện tại (dùng bởi middleware)
# ---------------------------------------------------------------------------


def _text(message: AnyMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _is_system_marker(message: AnyMessage) -> bool:
    return isinstance(message, HumanMessage) and _text(message).startswith(_SYSTEM_MARKERS)


def turn_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Các message SAU tin nhắn thật gần nhất của người dùng (bỏ qua tin nhắn nội bộ do
    middleware chèn). `ask_user` resume vẫn nằm trong cùng turn: đáp án đi vào state dưới
    dạng `ToolMessage`, không phải `HumanMessage` mới."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, HumanMessage) and not _is_system_marker(m):
            return messages[i + 1 :]
    return list(messages)


class TurnReasoning(BaseModel):
    has_valid_reasoning: bool = False
    has_evidence: bool = False
    # Có kết quả tool (bằng chứng) MỚI hơn lần lập luận hợp lệ gần nhất.
    pending_evidence: bool = False
    invalid_count: int = 0
    feedback_count: int = 0


def analyze_turn(turn: list[AnyMessage]) -> TurnReasoning:
    state = TurnReasoning()
    for m in turn:
        if isinstance(m, AIMessage):
            for call in m.tool_calls:
                if call["name"] != TOOL_NAME:
                    continue
                # Đếm lần không hợp lệ theo THAM SỐ (không dựa nội dung `ToolMessage`): lỗi schema
                # bị `ToolNode` bắt trước khi tool chạy nên không có `INVALID_PREFIX`.
                data, _ = validate_reasoning(call["args"])
                if data is not None:
                    state.has_valid_reasoning = True
                    state.pending_evidence = False
                else:
                    state.invalid_count += 1
        elif isinstance(m, ToolMessage):
            if m.name not in _NON_EVIDENCE_TOOLS:
                state.has_evidence = True
                state.pending_evidence = True
        elif _is_system_marker(m) and _text(m).startswith(FEEDBACK_PREFIX):
            state.feedback_count += 1
    return state


def has_valid_reasoning_call(message: AIMessage) -> bool:
    return any(
        call["name"] == TOOL_NAME and validate_reasoning(call["args"])[0] is not None
        for call in message.tool_calls
    )


def needs_reasoning(message: AIMessage) -> bool:
    """AIMessage gọi tool bằng chứng mà KHÔNG kèm `record_reasoning` hợp lệ trong cùng lượt gọi."""
    if not message.tool_calls or has_valid_reasoning_call(message):
        return False
    return any(c["name"] not in _NON_EVIDENCE_TOOLS for c in message.tool_calls)
