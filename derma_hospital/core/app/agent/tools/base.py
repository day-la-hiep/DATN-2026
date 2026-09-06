"""Hợp đồng chung cho 1 tool nghiệp vụ gắn vào node `reasoning` (`app/agent/graph.py`).

Đây là điểm mở rộng DUY NHẤT khi thêm tool mới: viết 1 module con định nghĩa 1
`ToolSpec` (xem `ask_user.py` làm ví dụ), rồi đăng ký vào `TOOL_SPECS`
(`app/agent/tools/__init__.py`). `graph.py` không còn biết tên tool cụ thể nào —
KHÔNG còn `if tool_call["name"] == "ask_user"` hard-code — chỉ tra registry theo
`tool_call["name"]` (`TOOLS_BY_NAME`).

2 kiểu tool, phân biệt bằng `requires_wait`:
  - `requires_wait=False` (mặc định, đa số tool nghiệp vụ): tool chạy trong ĐÚNG 1
    Reasoning "gọi tool" — `run()` được `await` ngay tại đó, có thể chạy khá lâu (gọi
    API ngoài, tra cứu tài liệu...) nhưng KHÔNG cần `interrupt()` vì không cần input
    từ bên ngoài graph trong lúc chờ.
  - `requires_wait=True`: tool cần tạm dừng graph chờ kết quả từ bên ngoài — con người
    trả lời (`ask_user`) hoặc 1 job async khác cần callback riêng — dùng
    `langgraph.types.interrupt()` (`kien-truc-agent.md` mục 3). `build_wait_request()`
    chạy ngay khi gặp tool_call để build payload gửi cho `interrupt()`; `on_resume()`
    chạy khi graph được resume (node `tool_wait`, xem `app/agent/graph.py`) để xử lý
    kết quả nhận được.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from langchain_core.messages.tool import ToolCall
from langchain_core.tools import StructuredTool

from app.dto.message import AnsweredChoiceDto, MessageChoiceDto


@dataclass(frozen=True)
class ToolWaitRequest:
    """`build_wait_request()` trả về — dùng để build `ReasoningResult` (Reasoning "gọi
    tool" đang tạm dừng) VÀ payload gửi nguyên vẹn cho `interrupt()`."""

    title: str
    payload: dict[str, Any]
    # Set nếu tool hiển thị dạng hỏi-chọn (như `ask_user`) — map vào
    # `ReasoningResult.choice` để FE render UI chọn (`kien-truc-agent.md` mục 3).
    # Tool chờ kiểu khác (vd chờ 1 job async xong) có thể để `None`.
    choice: MessageChoiceDto | None = None


@dataclass(frozen=True)
class ToolResumeResult:
    """`on_resume()` trả về sau khi `interrupt()` được resume (`Command(resume=...)`)."""

    tool_message_content: str
    # Set nếu muốn gắn `answered` vào `choice` của Reasoning đang chờ (chỉ có ý nghĩa
    # khi `ToolWaitRequest.choice` đã được set lúc `build_wait_request()`).
    answered: AnsweredChoiceDto | None = None


@dataclass(frozen=True)
class ToolSpec:
    """1 tool nghiệp vụ đăng ký cho node `reasoning`/`tool_wait`."""

    name: str
    tool: StructuredTool  # schema bind vào LLM (`app/agent/llm.py`)
    requires_wait: bool = False

    # Bắt buộc khi requires_wait=True.
    build_wait_request: Callable[[ToolCall, str], ToolWaitRequest] | None = None
    on_resume: Callable[[dict[str, Any]], ToolResumeResult] | None = None

    # Bắt buộc khi requires_wait=False.
    run: Callable[[ToolCall], Awaitable[str]] | None = None

    def __post_init__(self) -> None:
        if self.requires_wait:
            assert self.build_wait_request is not None and self.on_resume is not None, (
                f"Tool '{self.name}': requires_wait=True cần build_wait_request + on_resume."
            )
        else:
            assert self.run is not None, f"Tool '{self.name}': cần khai báo run()."
