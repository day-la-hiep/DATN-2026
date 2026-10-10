"""Graph tiền chẩn đoán"""

from typing import Any, cast

from langchain.agents import AgentState, create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.middleware import (
    AgentMiddleware,
)
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.store.base import BaseStore

from agent.context.agent_context import AgentContext
from agent.middleware.model import (
    enforce_initial_reasoning,
    force_reasoning,
    emit_reasoning_step,
    inject_long_term_memory,
    select_model,
)
from agent.middleware.evidence import (
    evidence_answer_check,
    evidence_reasoning_check,
    evidence_rules,
)
from agent.middleware.tool import emit_tool_result
from agent.prompt.orchestrator import DIAGNOSIS_PROMPT
from agent.tools.ask_user import ask_user
from agent.tools.hybrid_retrieval import (
    hybrid_retrieval,
    keyword_search,
    knowledge_graph_search,
    semantic_search,
)
from agent.tools.reasoning import record_reasoning
from agent.tools.skin_image_classifier import classify_skin_image
from agent.tools.web_search import fetch_trusted_page, search_trusted_web
from agent.common.llm import get_model
from agent.tools.memory import save_memory


ALL_TOOLS = [
    record_reasoning,
    ask_user,
    save_memory,
    hybrid_retrieval,
    semantic_search,
    keyword_search,
    knowledge_graph_search,
    classify_skin_image,
    search_trusted_web,
    fetch_trusted_page,
]


def default_middleware() -> list[
    AgentMiddleware[AgentState[Any], AgentContext, Any]
]:
    # cast chỉ để dẹp lỗi kiểu: `emit_tool_result` bị suy ra ContextT=None, lệch với các middleware khác.
    return cast(
        "list[AgentMiddleware[AgentState[Any], AgentContext, Any]]",
        [
            select_model,
            inject_long_term_memory,
            force_reasoning,
            enforce_initial_reasoning,
            evidence_rules,
            evidence_answer_check,
            # emit_reasoning_step,
            emit_tool_result,
            # đứng SAU `emit_tool_result` (lớp trong): lời từ chối của nó vẫn được ghi vào bước hiển thị như mọi lỗi `record_reasoning`
            evidence_reasoning_check,
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


def build_pre_diagnosis_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
    store: BaseStore | None = None,
    *,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware[AgentState[Any], AgentContext, Any]]
    | None = None,
) -> CompiledStateGraph[Any, AgentContext, Any, Any]:
    """`checkpointer` / `store` để None khi nối vào chat graph"""
    return create_agent(
        get_model(),
        tools=ALL_TOOLS if tools is None else tools,
        system_prompt=DIAGNOSIS_PROMPT
        if system_prompt is None
        else system_prompt,
        middleware=default_middleware() if middleware is None else middleware,
        context_schema=AgentContext,
        checkpointer=checkpointer,
        store=store,
        name="pre_diagnosis",
    )
