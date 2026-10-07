"""Context riêng cho từng lần chạy graph (LangGraph 1.x `context_schema`).

Thay cho cách cũ nhét `user_id`/`conversation_id` vào `config["configurable"]` — truyền
vào lúc gọi graph qua tham số `context=` (`agent/turn.py::_stream_graph`),
đọc lại trong node/tool bằng cách khai tham số `runtime: Runtime[AgentContext]` (node,
`pre_model_hook`) hoặc `runtime: ToolRuntime` (tool) — LangGraph tự inject theo TÊN tham
số `runtime`, không cần truyền tay qua từng hàm.

`thread_id` (cho checkpointer, xem `agent/graph/chat_graph.py`) KHÔNG nằm ở đây — đó là tham số
hạ tầng của LangGraph (`config["configurable"]["thread_id"]`), tách khỏi context nghiệp
vụ này dù trong hệ thống hiện tại giá trị của nó luôn trùng `conversation_id`.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    user_id: str
    conversation_id: str
    # `message_id` của turn hiện tại — dùng bởi middleware `_emit_llm_steps`
    # (`agent/graph/pre_diagnosis_graph.py`) để publish event `message.llm_step` đúng `messageId` (khớp
    # schema `base` dict của `worker.py::_drive`, FE cần field này để gắn event vào đúng
    # tin nhắn đang stream). Rỗng an toàn cho code cũ/test không cần stream (context chỉ
    # thiếu field optional này, không crash).
    message_id: str = ""
    # `object_key` các ảnh đính kèm của turn hiện tại — `classify_skin_image` đối chiếu
    # tham số LLM truyền vào với danh sách này vì LLM hay chép sai chuỗi hex dài.
    image_keys: list[str] = field(default_factory=list)
    # Chuỗi "provider:model" (KHÔNG phải id ngắn) của conversation hiện tại — worker đã
    # resolve từ `Conversation.model` qua `AGENT_MODEL_CHOICES` (`app/config/settings.py`)
    # trước khi build context này, xem `agent/worker.py::_conversation_for`. Rỗng ->
    # middleware `select_model` (`agent/graph/pre_diagnosis_graph.py`) fallback `settings.AGENT_MODEL`.
    model: str = ""
    # Tích luỹ TRỰC TIẾP bởi `emit_reasoning_step`/`emit_tool_result` (`agent/middleware/`)
    # — mỗi dict khớp field (snake_case) của `Step` (`app/dto/common/chat.py`).
    # `worker.py::_drive` giữ CÙNG reference `AgentContext` truyền vào
    # `agent_graph.astream(..., context=context, ...)` nên middleware append vào đây thì
    # đọc lại được NGAY sau khi `astream()` xong (không cần kênh truyền riêng) — forward
    # qua `AgentResponseMessage.reasoning` để Core persist vào `Message.extra.reasoning`,
    # có vậy load lại hội thoại (`GET .../messages`) mới thấy được các bước suy luận thay
    # vì chỉ thấy lúc đang stream (SSE không replay được).
    reasoning_steps: list[dict[str, Any]] = field(default_factory=list)
