"""Tool `ask_user` — hỏi lại người dùng (`kien-truc-agent.md` mục 3).

Tool ĐẦU TIÊN dùng cơ chế chờ tổng quát `ToolSpec.requires_wait=True`
(`app/agent/tools/base.py`) — cũng là ví dụ mẫu cho tool cần chờ lâu sau này (chờ
không nhất thiết phải là hỏi người dùng, có thể là 1 job async khác cần callback).

Chỉ khai báo **schema** cho LLM gọi — node `reasoning`/`tool_wait`
(`app/agent/graph.py`) tự tra `ToolSpec` này theo tên, luôn điều hướng sang
`tool_wait` (pause bằng `interrupt()`) thay vì gọi hàm `func` bên dưới. Hàm
`_unreachable` không bao giờ chạy thật; để đó chỉ vì `StructuredTool.from_function`
yêu cầu 1 callable.
"""
import json
from typing import Any

from langchain_core.messages.tool import ToolCall
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent.tools.base import ToolResumeResult, ToolSpec, ToolWaitRequest
from app.dto.message import AnsweredChoiceDto, ChoiceOptionDto, MessageChoiceDto

ASK_USER_TOOL_NAME = "ask_user"


class AskUserArgs(BaseModel):
    question: str = Field(description="Câu hỏi ngắn gọn để hỏi lại người dùng.")
    options: list[str] = Field(
        default_factory=list,
        description="Danh sách lựa chọn gợi ý (để rỗng nếu muốn người dùng tự nhập).",
    )


def _unreachable(question: str, options: list[str] | None = None) -> str:
    raise RuntimeError(
        "ask_user không được thực thi trực tiếp — phải qua node tool_wait "
        "(xem app/agent/graph.py)."
    )


def _build_wait_request(tool_call: ToolCall, step_id: str) -> ToolWaitRequest:
    args = tool_call["args"]
    options = [
        ChoiceOptionDto(id=f"opt-{i}", label=label)
        for i, label in enumerate(args.get("options") or [])
    ]
    choice = MessageChoiceDto(
        question_id=f"{step_id}-q",
        question=args.get("question", ""),
        options=options,
    )
    return ToolWaitRequest(
        title="Cần hỏi thêm thông tin",
        payload=choice.model_dump(mode="json"),
        choice=choice,
    )


def _on_resume(answer: dict[str, Any]) -> ToolResumeResult:
    # `answer` tới từ `TurnRequest.answer` (nội bộ, không qua CamelModel) — key
    # snake_case, KHÁC với JSON camelCase trên wire API (`MessageAnswerDto`).
    answered = AnsweredChoiceDto(
        option_id=str(answer.get("option_id", "")),
        label=str(answer.get("label", "")),
        custom=bool(answer.get("custom", False)),
    )
    return ToolResumeResult(tool_message_content=json.dumps(answer), answered=answered)


ask_user_tool = StructuredTool.from_function(
    func=_unreachable,
    name=ASK_USER_TOOL_NAME,
    description=(
        "Hỏi lại người dùng khi thiếu thông tin quan trọng để trả lời câu hỏi hiện tại. "
        "Turn sẽ tạm dừng, chờ người dùng chọn/nhập rồi mới tiếp tục."
    ),
    args_schema=AskUserArgs,
)

ASK_USER_SPEC = ToolSpec(
    name=ASK_USER_TOOL_NAME,
    tool=ask_user_tool,
    requires_wait=True,
    build_wait_request=_build_wait_request,
    on_resume=_on_resume,
)
