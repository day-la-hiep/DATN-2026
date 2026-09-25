"""Agent graph — dùng `create_agent` (`langchain.agents`, kế thừa
`langgraph.prebuilt.create_react_agent` cũ đã deprecated) thay vì tự dựng lại vòng lặp
"gọi LLM ⇄ gọi tool" bằng `StateGraph` thủ công. `create_agent` cho sẵn: vòng lặp ReAct
chuẩn, `ToolNode` thực thi tool (kể cả tool tự `interrupt()` —
`app/agent/tools.py::ask_user`), checkpointer (short-term memory theo `thread_id`) và
`store` (long-term memory xuyên thread, `app/agent/memory.py`).

Phần còn lại tuỳ biến qua `middleware` (cơ chế mở rộng CÓ SẴN của `create_agent`, xem
`langchain.agents.middleware`) thay vì tự viết node/hook riêng:
  - `SummarizationMiddleware` (có sẵn): tự tóm tắt lịch sử hội thoại cũ khi vượt
    ngưỡng — quản lý short-term memory tốt hơn cắt/bỏ tin nhắn (không mất thông tin,
    chỉ nén lại).
  - `select_model` (`wrap_model_call`, đứng ĐẦU middleware): override model theo
    `AgentContext.model` — model chọn theo TỪNG conversation (`Conversation.model`,
    `app/core/config.py::AGENT_MODEL_CHOICES`), không còn 1 model cố định toàn hệ thống.
  - `inject_long_term_memory` (`wrap_model_call`, phải tự viết vì đây là logic
    nghiệp vụ — LangChain không biết trước "nhớ gì" cho app cụ thể): trước mỗi lần gọi
    LLM, semantic search long-term memory liên quan (`app/agent/memory.py`) rồi chèn
    vào `system_message`.
  - `emit_reasoning_step` (`wrap_model_call`) + `emit_tool_result` (`wrap_tool_call`):
    nguồn phát SSE DUY NHẤT cho 2 event `message.thinking`/`message.tool_result` — trước
    đây `worker.py::_drive` tự trích 2 event này từ state diff của `astream()`, nay
    chuyển hẳn vào middleware để: (a) bắt được MỌI lần gọi LLM/tool trong vòng lặp ReAct
    kể cả khi provider không trả "thinking" block (tự tổng hợp từ `tool_calls` +
    `TOOL_DISPLAY_NAMES`), (b) giữ NGUYÊN shape event cũ — FE không cần đổi gì.
  - `critic_review` (`after_model`, dùng cơ chế `jump_to` CÓ SẴN của `create_agent` —
    KHÔNG tự dựng `StateGraph`/node riêng): chạy sau MỖI lần model trả lời; câu trả lời
    KHÔNG kèm `tool_calls` (coi như bản nháp cuối, sắp kết thúc turn) VÀ turn có tra cứu
    tool (không áp dụng cho chào hỏi/ngoài phạm vi, mục 2 SYSTEM_PROMPT) → 1 lệnh gọi LLM
    riêng (critic) chấm bản nháp theo mục 1/7/8 SYSTEM_PROMPT (bằng chứng, cờ đỏ, không
    kê đơn, có nêu độ tin cậy). Đạt → cho qua (`return None`, để routing mặc định sang
    "end"). Chưa đạt → chèn feedback + `jump_to="model"` bắt trả lời lại, tối đa
    `MAX_CRITIC_RETRIES` lần/turn (tránh treo turn vô thời hạn nếu model không bao giờ
    đạt).
"""

from typing import Any, cast

from langchain.agents import AgentState, create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.middleware import (
    AgentMiddleware,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.store.base import BaseStore

from agent.state.context import AgentContext
from agent.middleware.model import (
    emit_reasoning_step,
    inject_long_term_memory,
    select_model,
)
from agent.middleware.tool import emit_tool_result
from agent.prompt.orchestrator import SYSTEM_PROMPT
from agent.tools.ask_user import ask_user
from agent.tools.dermo_terms import lookup_dermo_term
from agent.tools.entity_grounding import ground_medical_entities
from agent.tools.expand_context import expand_entity_context
from agent.tools.knowledge_base_search import (
    get_disease_guideline_profile,
    search_disease_guidelines,
)
from agent.tools.knowledge_graph import query_dermatology_kg
from agent.tools.plan import make_plan
from agent.tools.skin_image_classifier import classify_skin_image
from agent.llm import get_model
from agent.tools.memory import (
    build_memory_store,
    save_memory,
)


ALL_TOOLS = [
    make_plan,
    ask_user,
    save_memory,
    query_dermatology_kg,
    lookup_dermo_term,
    ground_medical_entities,
    expand_entity_context,
    search_disease_guidelines,
    get_disease_guideline_profile,
    classify_skin_image,
]


def default_middleware() -> list[
    AgentMiddleware[AgentState[Any], AgentContext, Any]
]:
    # `cast` CHỈ để dẹp lỗi kiểu tĩnh, KHÔNG đổi hành vi runtime: `ToolCallRequest`
    # (dùng bởi `emit_tool_result`, `@wrap_tool_call`) không phải generic — Pylance tự
    # suy ra `ContextT=None` cho middleware đó, lệch với các middleware còn lại
    # (`@wrap_model_call` trên `ModelRequest[AgentContext]` → `ContextT=AgentContext`),
    # khiến cả list bị coi là union 2 kiểu không tương thích (`ContextT` invariant).
    # `create_agent` không hề đọc type param này lúc chạy nên cast an toàn.
    return cast(
        "list[AgentMiddleware[AgentState[Any], AgentContext, Any]]",
        [
            select_model,
            inject_long_term_memory,
            # emit_reasoning_step,
            emit_tool_result,
            # critic_review,
            # trigger/keep tính theo SỐ TIN NHẮN — đơn giản, không cần tokenizer riêng
            # cho từng provider. Vượt 20 tin nhắn -> tóm tắt còn lại 10 tin gần nhất.
            # SummarizationMiddleware(
            #     model=get_model(),
            #     trigger=("messages", 20),
            #     keep=("messages", 10),
            # ),
        ],
    )


def build_agent_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    *,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware[AgentState[Any], AgentContext, Any]]
    | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """`tools`/`system_prompt`/`middleware` chỉ để thử nghiệm luồng lập luận (xem skill
    `experiment-agent-flow`) — production luôn để mặc định (`ALL_TOOLS`, `SYSTEM_PROMPT`,
    `default_middleware()`)."""
    return create_agent(
        get_model(),
        tools=ALL_TOOLS if tools is None else tools,
        system_prompt=SYSTEM_PROMPT if system_prompt is None else system_prompt,
        middleware=default_middleware() if middleware is None else middleware,
        context_schema=AgentContext,
        # InMemorySaver/InMemoryStore: đủ cho dev (worker 1 tiến trình duy nhất).
        # Production cần backend bền vững hơn — xem `agent/tools/memory.py`.
        checkpointer=checkpointer or InMemorySaver(),
        store=store or build_memory_store(),
    )


agent_graph = build_agent_graph()


def config_for(conversation_id: str) -> RunnableConfig:
    """`thread_id` = `conversation_id`: checkpointer nối liền TOÀN BỘ hội thoại (mọi
    turn cùng 1 thread) — khác bản trước (`thread_id = message_id` riêng từng turn, xem
    `kien-truc-memory.md` mục 0), nay không cần tầng memory riêng ghép lại các turn vì
    checkpointer đã tự làm việc đó qua `messages`. Dùng chung bởi mọi caller chạy
    `agent_graph` (`app/agent/worker.py`)."""
    return {"configurable": {"thread_id": conversation_id}}
