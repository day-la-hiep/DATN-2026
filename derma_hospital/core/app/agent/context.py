"""Context riêng cho từng lần chạy graph (LangGraph 1.x `context_schema`).

Thay cho cách cũ nhét `user_id`/`conversation_id` vào `config["configurable"]` — truyền
vào lúc gọi graph qua tham số `context=` (`app/agent/graph.py::run_turn`/`resume_turn`),
đọc lại trong node/tool bằng cách khai tham số `runtime: Runtime[AgentContext]` (node,
`pre_model_hook`) hoặc `runtime: ToolRuntime` (tool) — LangGraph tự inject theo TÊN tham
số `runtime`, không cần truyền tay qua từng hàm.

`thread_id` (cho checkpointer, xem `app/agent/graph.py`) KHÔNG nằm ở đây — đó là tham số
hạ tầng của LangGraph (`config["configurable"]["thread_id"]`), tách khỏi context nghiệp
vụ này dù trong hệ thống hiện tại giá trị của nó luôn trùng `conversation_id`.
"""
from dataclasses import dataclass


@dataclass
class AgentContext:
    user_id: str
    conversation_id: str
