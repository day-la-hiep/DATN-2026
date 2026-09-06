"""State cho vòng lặp Turn/Step/Reasoning (`kien-truc-agent.md`).

Phân tầng đúng theo tài liệu:
  - `TurnState.steps`: các Step đã đóng (Reasoning cuối cùng không còn tool call).
  - `TurnState.current_step`: Reasoning của Step đang chạy dở, tích luỹ dần.
"""
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from app.dto.message import MessageChoiceDto, ReasoningStepDto


class ReasoningResult(BaseModel):
    """1 Reasoning đã hoàn tất — map 1-1 sang chuỗi event
    `reasoning.step_started/_delta/_completed` (worker.py tự chunk `content` để giả lập
    stream, xem `app/agent/worker.py`).

    QUAN TRỌNG: 1 Reasoning là **đúng 1 hành động** — HOẶC gọi LLM (`step_type="default"`),
    HOẶC thực thi 1 tool mà Reasoning gọi LLM ngay trước đó vừa yêu cầu
    (`step_type="tool_call"`/`"tool_ask"`) — KHÔNG bao giờ gộp cả 2 vào 1 Reasoning. 1 Step
    là 1 chuỗi nhiều Reasoning xen kẽ: gọi LLM → (nếu LLM yêu cầu) thực thi tool → gọi LLM
    (với kết quả tool) → ... tới khi 1 lần gọi LLM không yêu cầu tool nào nữa.

    LƯU Ý: field ở đây (`step_id`/`step_type`/`step_continues`) là shape NỘI BỘ của agent,
    KHÔNG trùng tên với `ReasoningStepDto` (wire DTO — `id`/`status`/`type`,
    `app/dto/message.py`). Dùng `to_dto()` khi cần gửi ra ngoài (SSE `message.done`, persist
    vào `messages.extra.reasoning`) — KHÔNG `model_dump()` trực tiếp instance này ra wire,
    nếu không `MessageMetadataDto` sẽ validate lỗi thiếu field `id`/`status`.
    """

    step_id: str
    title: str
    content: str
    step_type: Literal["default", "tool_call", "tool_ask"] = "default"
    choice: MessageChoiceDto | None = None  # chỉ có khi step_type="tool_ask"
    step_continues: bool  # false CHỈ khi đây là 1 lần gọi LLM không yêu cầu tool nào -> Step kết thúc

    def to_dto(self) -> ReasoningStepDto:
        """Map sang shape wire (`ReasoningStepDto`). `status="done"` cố định: 1
        `ReasoningResult` chỉ được append vào state SAU KHI đã hoàn tất (gọi LLM xong hoặc
        tool đã chạy/đã build xong câu hỏi) — không có khái niệm "processing" ở tầng
        persist/`message.done`, khác với FE tự set `status="processing"` tạm thời lúc
        đang nhận `reasoning.step_delta` real-time."""
        return ReasoningStepDto(
            id=self.step_id,
            title=self.title,
            content=self.content,
            status="done",
            type=self.step_type,
            choice=self.choice,
        )


class StepResult(BaseModel):
    """1 Step đã đóng = danh sách Reasoning liên tiếp."""

    reasoning: list[ReasoningResult]


class PendingTool(BaseModel):
    """Trạng thái chờ tổng quát khi 1 tool `requires_wait=True` tạm dừng graph bằng
    `interrupt()` (`app/agent/tools/base.py`) — generic hoá `pending_question`/
    `pending_tool_call_id` của bản trước (vốn hard-code riêng cho `ask_user`). Node
    `tool_wait` (`app/agent/graph.py`) tra `tool_name` trong registry
    (`app/agent/tools.TOOLS_BY_NAME`) để biết cách xử lý resume, KHÔNG hard-code tên
    tool cụ thể nào."""

    tool_call_id: str
    tool_name: str
    payload: dict[str, object]  # gửi nguyên vẹn cho `interrupt()`


class TurnState(TypedDict):
    conversation_id: str
    message_id: str  # id assistant message của cả turn (ổn định qua mọi Step/resume)
    # `add_messages` gộp message mới vào list thay vì ghi đè — chuẩn LangGraph.
    messages: Annotated[list[AnyMessage], add_messages]
    steps: list[StepResult]
    current_step: list[ReasoningResult]  # Reasoning của Step đang mở, chưa đóng
    step_count: int  # đếm theo Reasoning toàn turn (giới hạn an toàn, không phải theo Step)
    just_closed_step: bool  # true ngay sau Reasoning "gọi LLM" mà không yêu cầu tool nào
    outcome: Literal["continue", "answer"] | None  # kết quả pre_step gần nhất
    final_answer: str | None
    pending_tool: PendingTool | None  # tool `requires_wait=True` đang chờ interrupt() resume
    # Nội dung Steer vừa được `pre_step` append vào context ở lần chạy gần nhất — worker.py
    # đọc field này để publish `message.steered` (rỗng khi không có Steer nào, mục 5).
    last_steer_batch: list[str]
