"""Registry tool nghiệp vụ cho node `reasoning` (`app/agent/graph.py`).

Thêm tool mới:
  1. Viết 1 module con định nghĩa 1 `ToolSpec` (xem `base.py` cho hợp đồng,
     `ask_user.py` làm ví dụ tool `requires_wait=True`).
  2. Thêm `ToolSpec` đó vào `TOOL_SPECS` dưới đây.

KHÔNG cần sửa `graph.py` — node `reasoning`/`tool_wait` tra tool theo tên qua
`TOOLS_BY_NAME`, và `_run_llm` bind toàn bộ `ALL_TOOLS` vào LLM.
"""
from app.agent.tools.ask_user import ASK_USER_SPEC, ASK_USER_TOOL_NAME
from app.agent.tools.base import ToolResumeResult, ToolSpec, ToolWaitRequest

TOOL_SPECS: list[ToolSpec] = [ASK_USER_SPEC]
TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}
ALL_TOOLS = [spec.tool for spec in TOOL_SPECS]  # bind vào LLM (`app/agent/llm.py`)

__all__ = [
    "TOOL_SPECS",
    "TOOLS_BY_NAME",
    "ALL_TOOLS",
    "ToolSpec",
    "ToolWaitRequest",
    "ToolResumeResult",
    "ASK_USER_TOOL_NAME",
]
