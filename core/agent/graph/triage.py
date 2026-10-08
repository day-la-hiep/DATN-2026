"""Node lọc intent của chat graph"""
import logging
from typing import Any, Literal

from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.llm import get_model
from agent.prompt.triage import TRIAGE_SYSTEM
from agent.state.chat_state import ChatState
from agent.state.context import AgentContext
from app.config.settings import settings

logger = logging.getLogger(__name__)

_CONTEXT_MESSAGES = 6  # số tin gần nhất đưa vào để hiểu ngữ cảnh ("vâng", "3 ngày" là tiếp nối câu hỏi y khoa)
_CONTEXT_CHARS = 300
# `turn._human_message_content` gắn dòng này vào tin có ảnh: ảnh luôn cần graph tiền chẩn đoán, khỏi tốn một lần gọi LLM
_IMAGE_MARKER = "[Ảnh đính kèm]"


class TriageDecision(BaseModel):
    route: Literal["answer", "diagnose"]
    reply: str = Field(default="", description="Câu trả lời ngắn khi route=answer; để trống khi route=diagnose")


def _text(message: AnyMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _transcript(messages: list[AnyMessage]) -> str:
    """Vài tin gần nhất dạng văn bản (bỏ tin tool và tin AI không có chữ), tin cuối là tin cần phân loại."""
    lines = [
        f"{'Người dùng' if isinstance(m, HumanMessage) else 'Trợ lý'}: {_text(m).strip()[:_CONTEXT_CHARS]}"
        for m in messages
        if isinstance(m, (HumanMessage, AIMessage)) and _text(m).strip()
    ][-_CONTEXT_MESSAGES:]
    return "\n".join(lines)


async def classify(messages: list[AnyMessage], model: str) -> TriageDecision:
    structured = get_model(model or None).with_structured_output(TriageDecision, method="function_calling")
    result = await structured.ainvoke([SystemMessage(content=TRIAGE_SYSTEM), HumanMessage(content=_transcript(messages))])
    assert isinstance(result, TriageDecision)
    return result


async def triage(state: ChatState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    messages = state["messages"]
    last = messages[-1] if messages else None
    if not isinstance(last, HumanMessage) or _IMAGE_MARKER in _text(last):
        return {"route": "diagnose"}
    try:
        decision = await classify(messages, settings.AGENT_TRIAGE_MODEL or runtime.context.model)
    except Exception as exc:  # noqa: BLE001 — triage hỏng không được chặn câu hỏi y khoa
        logger.warning("lỗi, chuyển sang graph tiền chẩn đoán: %s", exc)
        return {"route": "diagnose"}
    if decision.route != "answer" or not decision.reply.strip():
        return {"route": "diagnose"}
    return {"route": "answer", "messages": [AIMessage(content=decision.reply.strip())]}
