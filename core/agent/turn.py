"""Xử lý 1 turn của agent"""

import json
import logging
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command, Interrupt

from agent.dto.schemas import AgentResponseMessage, TurnRequest
from agent.graph.chat_graph import chat_graph, config_for
from agent.context.agent_context import AgentContext
from agent.context.builder import build_context
from app.api.deps import get_rabbitmq_client, get_redis_client
from app.config.constants import (
    AGENT_EVENTS_CHANNEL,
    AGENT_RESPONSE_QUEUE,
    STREAM_DONE_SENTINEL,
)
from app.dto.common import ChoiceOption, MessageChoice

logger = logging.getLogger(__name__)

# Node của chat graph có thể tạo câu trả lời cuối của turn: bước lọc intent trả lời luôn (`triage`) hoặc graph tiền chẩn đoán
# (`pre_diagnosis`; update của nó gồm mọi tin mới trong vòng lặp nên câu trả lời là AIMessage cuối cùng).
_ANSWER_NODES = ("triage", "pre_diagnosis")

_ERROR_TEXT = (
    "Xin lỗi, hệ thống gặp sự cố khi xử lý câu hỏi này (có thể do quá tải "
    "tạm thời). Vui lòng thử lại sau ít phút."
)


def _human_message_content(req: TurnRequest) -> str:
    """Nối thêm object key MinIO của ảnh đính kèm"""
    content = req.content or ""
    images = [
        a
        for a in (req.attached_files or [])
        if a.content_type.startswith("image/")
    ]
    if not images:
        return content

    # nhãn `object_key` giữ nguyên: là tên tham số của tool `classify_skin_image` mà prompt hướng dẫn LLM chép lại
    lines = [
        f'- name="{a.file_name}" object_key="{a.storage_key}"' for a in images
    ]
    return content + "\n\n[Ảnh đính kèm]\n" + "\n".join(lines)


async def _stream_graph(
    input_: object,
    channel: str,
    base: dict[str, Any],
    context: AgentContext,
    req: TurnRequest,
) -> tuple[AIMessage | None, Interrupt | None]:
    """Chạy chat graph, forward token; trả `(AIMessage cuối, Interrupt nếu tạm dừng)`."""
    interrupt: Interrupt | None = None
    final_message: AIMessage | None = None
    streamed = False

    async for mode, chunk in chat_graph.astream(  # pyright: ignore[reportUnknownMemberType]
        input_,
        config=config_for(req.conversation_id),
        context=context,
        stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            # token model chính do node `pre_diagnosis` của chat graph chuyển tiếp (`agent/graph/chat_graph.py::_pre_diagnosis_node`)
            payload = cast("dict[str, Any]", chunk)
            if payload.get("type") == "token" and payload.get("text"):
                streamed = True
                await emit(
                    channel,
                    {"type": "message.delta", "delta": payload["text"], **base},
                )
            continue

        # mode == "updates": state diff sau mỗi node của chat graph — dùng để phát hiện interrupt (tool `ask_user`) và tóm `AIMessage`
        # cuối cùng (LangGraph đã gộp sẵn, không cần tự cộng dồn từng chunk). Token không đi qua đây mà qua mode "custom" ở trên.
        update = cast(dict[str, Any], chunk)
        if "__interrupt__" in update:
            interrupt = cast(tuple[Interrupt, ...], update["__interrupt__"])[0]
            break
        for node in _ANSWER_NODES:
            node_update = update.get(node)
            if node_update and node_update.get("messages"):
                last = node_update["messages"][-1]
                if isinstance(last, AIMessage):
                    final_message = last

    # Câu trả lời của triage không đi qua token streaming (nằm trong tham số tool của lần phân loại) — phát một lần để FE hiển thị
    # như các câu trả lời khác.
    if (
        interrupt is None
        and final_message is not None
        and not streamed
        and final_message.text
    ):
        await emit(
            channel,
            {"type": "message.delta", "delta": final_message.text, **base},
        )

    return final_message, interrupt


async def _finish_with_question(
    channel: str,
    base: dict[str, Any],
    req: TurnRequest,
    interrupt: Interrupt,
    context: AgentContext,
) -> None:
    """Turn tạm dừng ở tool `ask_user`"""
    raw: Any = interrupt.value
    payload: dict[str, Any] = (
        cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    )
    choice = MessageChoice(
        question_id=interrupt.id,
        question=str(payload.get("question", "")),
        options=[
            ChoiceOption(id=f"opt-{i}", label=str(label))
            for i, label in enumerate(payload.get("options") or [])
        ],
    )
    choice_json = choice.model_dump(mode="json")
    await finish_turn(
        channel,
        req,
        {"type": "message.question", "choice": choice_json, **base},
        content="",
        status="question",
        choice=choice_json,
        reasoning=context.reasoning_steps,
    )


async def _drive(req: TurnRequest, input_: object) -> None:
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=req.conversation_id)
    context = await build_context(req)
    base: dict[str, Any] = {
        "conversation_id": req.conversation_id,
        "message_id": req.message_id,
    }

    await emit(
        channel, {"type": "message.started", "corr_id": req.corr_id, **base}
    )

    try:
        final_message, interrupt = await _stream_graph(
            input_, channel, base, context, req
        )
    except Exception as exc:  # noqa: BLE001
        # Không để lỗi lọt ra ngoài (turn sẽ treo, message kẹt "queued"); coi như "done" với nội dung báo lỗi
        # vì thêm status "error" phải sửa cả DTO/FE/DB enum.
        logger.exception("lỗi khi chạy turn %s: %s", req.message_id, exc)
        await finish_turn(
            channel,
            req,
            {"type": "message.done", "content": _ERROR_TEXT, **base},
            content=_ERROR_TEXT,
            status="done",
            reasoning=context.reasoning_steps,
        )
        return

    if interrupt is not None:
        await _finish_with_question(channel, base, req, interrupt, context)
        return

    answer = final_message.text if final_message is not None else ""
    await finish_turn(
        channel,
        req,
        {"type": "message.done", "content": answer, **base},
        content=answer,
        status="done",
        reasoning=context.reasoning_steps,
    )


async def handle_turn(req: TurnRequest) -> None:
    """Turn mới."""
    await _drive(
        req, {"messages": [HumanMessage(content=_human_message_content(req))]}
    )


async def handle_resume(req: TurnRequest) -> None:
    """Tiếp tục turn đang dừng ở `ask_user` với câu trả lời của người dùng."""
    await _drive(req, Command(resume=req.answer))


async def emit(channel: str, payload: dict[str, Any]) -> None:
    await get_redis_client().publish(channel, json.dumps(payload))


async def finish_turn(
    channel: str,
    req: TurnRequest,
    event: dict[str, Any],
    *,
    content: str,
    status: Literal["done", "question"],
    choice: dict[str, Any] | None = None,
    reasoning: list[dict[str, Any]] | None = None,
) -> None:
    """Kết thúc/tạm dừng turn"""
    await emit(channel, event)
    await get_redis_client().publish(channel, STREAM_DONE_SENTINEL)
    await get_rabbitmq_client().publish(
        AGENT_RESPONSE_QUEUE,
        AgentResponseMessage(
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            content=content,
            status=status,
            choice=choice,
            reasoning=reasoning or None,
        )
        .model_dump_json()
        .encode("utf-8"),
    )
