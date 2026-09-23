"""Agent worker — tiến trình riêng, tách khỏi FastAPI process.

Luồng:
  1. consume RabbitMQ `agent_request_queue` (Core đẩy turn mới/Steer/resume, xem
     `app/agent/schemas.py::TurnRequest`).
  2. chạy `app/agent/graph.py::agent_graph` (`create_agent`), forward token thật (LangGraph
     `stream_mode="messages"`, KHÔNG tự chunk giả lập) lên Redis `agent:events:{id}`
     (`kien-truc-he-thong.md` mục 3) theo thời gian thực. `message.thinking`/
     `message.tool_result` (bước suy luận + kết quả tool) được phát trực tiếp từ
     middleware trong lúc graph chạy (`_emit_reasoning_step`/`_emit_tool_result`,
     `app/agent/graph.py`), KHÔNG phải từ vòng lặp `astream()` dưới đây.
  3. Khi turn tạm dừng (tool `ask_user` gọi `interrupt()`, `status="question"`) hoặc kết
     thúc (`status="done"`), publish `AgentResponseMessage` vào RabbitMQ
     `agent_response_queue` — Worker KHÔNG đụng Postgres, Core là consumer duy nhất làm
     upsert (`app/agent/response_consumer.py`).

`thread_id` (checkpointer) = `conversation_id` — 1 hội thoại = 1 thread duy nhất, mọi
turn nối tiếp qua `messages` (khác bản Turn/Step/Reasoning cũ dùng `thread_id =
message_id` riêng từng turn + tầng memory Qdrant riêng để ghép lại, xem
`app/agent/graph.py`).

Chạy: cd core && python -m app.agent.worker
"""
import asyncio
import json
from collections import defaultdict
from typing import Any, cast

from aio_pika.abc import AbstractIncomingMessage
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command, Interrupt

from app.agent.context import AgentContext
from app.agent.graph import agent_graph, config_for
from app.agent.schemas import AgentResponseMessage, TurnRequest
from app.core.config import log_startup_infra, settings
from app.core.constants import (
    AGENT_EVENTS_CHANNEL,
    AGENT_REQUEST_QUEUE,
    AGENT_RESPONSE_QUEUE,
    STREAM_DONE_SENTINEL,
)
from app.db.session import AsyncSessionLocal
from app.dto.message import ChoiceOptionDto, MessageChoiceDto
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import publish as redis_publish
from app.repositories.conversation_repository import ConversationRepository

# 1 Lock/conversation_id — `create_agent` KHÔNG hỗ trợ 2 lần `ainvoke()` đồng thời trên
# CÙNG `thread_id` (đụng checkpoint). Turn/Steer mới tới khi turn TRƯỚC của CÙNG hội
# thoại chưa xong sẽ CHỜ tới lượt thay vì chen ngang giữa chừng (đánh đổi có chủ đích —
# đơn giản hơn nhiều so với node `pre_step` tự dựng của bản trước, chấp nhận Steer chỉ
# thực sự được xử lý ngay SAU khi turn hiện tại xong thay vì ngay lập tức).
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _emit(channel: str, payload: dict[str, Any]) -> None:
    await redis_publish(channel, json.dumps(payload))


async def _conversation_for(conversation_id: str) -> tuple[str, str]:
    """`(user_id, model)` — `model` đã resolve từ id ngắn (`Conversation.model`) sang
    chuỗi "provider:model" thật qua `AGENT_MODEL_CHOICES` (`app/core/config.py`). Id
    rỗng/không còn trong `AGENT_MODEL_CHOICES` (model bị gỡ khỏi danh sách sau khi
    conversation đã chọn) -> trả rỗng, `AgentContext.model` rỗng -> `graph.py::_select_model`
    tự fallback `settings.AGENT_MODEL`."""
    async with AsyncSessionLocal() as db:
        conversation = await ConversationRepository(db).get(conversation_id)
    if conversation is None:
        return "", ""
    model = settings.AGENT_MODEL_CHOICES.get(conversation.model, "")
    return conversation.user_id, model


async def _drive(req: TurnRequest, input_: object) -> None:
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=req.conversation_id)
    config = config_for(req.conversation_id)
    user_id, model = await _conversation_for(req.conversation_id)
    context = AgentContext(
        user_id=user_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[
            a.object_key for a in (req.attachments or []) if a.type.startswith("image/")
        ],
        model=model,
    )
    base: dict[str, Any] = {"conversationId": req.conversation_id, "messageId": req.message_id}

    await _emit(channel, {"type": "message.started", "corrId": req.corr_id, **base})

    interrupt: Interrupt | None = None
    final_message: AIMessage | None = None

    try:
        async for mode, chunk in agent_graph.astream(
            input_, config=config, context=context, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                msg, meta = chunk
                assert isinstance(msg, BaseMessage)
                # `langgraph_node == "model"` lọc đúng token của LLM chính — bỏ qua các
                # lần gọi model nội bộ khác (vd `SummarizationMiddleware` tự gọi LLM tóm
                # tắt khi vượt ngưỡng, `app/agent/graph.py`), không lẫn vào stream trả
                # lời user.
                if meta.get("langgraph_node") == "model" and msg.text:
                    await _emit(channel, {"type": "message.delta", "delta": msg.text, **base})
                continue

            # mode == "updates": state diff sau mỗi node — dùng để phát hiện interrupt
            # (tool `ask_user`, `app/agent/tools.py`) và tóm được `AIMessage` cuối cùng
            # (không cần tự cộng dồn từng chunk, LangGraph đã gộp sẵn khi node "model"
            # hoàn tất).
            chunk = cast(dict[str, Any], chunk)
            if "__interrupt__" in chunk:
                interrupt = cast(tuple[Interrupt, ...], chunk["__interrupt__"])[0]
                break
            # `message.thinking`/`message.tool_result` KHÔNG còn phát từ đây — chuyển hẳn
            # vào middleware `_emit_reasoning_step`/`_emit_tool_result`
            # (`app/agent/graph.py`), chạy trong chính lượt gọi LLM/tool nên bắt được MỌI
            # lần gọi (kể cả khi loop `astream()` này chưa kịp yield state diff tương
            # ứng). Ở đây chỉ còn cần tóm `AIMessage` cuối cùng cho `message.done`.
            model_update = chunk.get("model")
            if model_update:
                final_message = cast(AIMessage, model_update["messages"][-1])
    except Exception as exc:  # noqa: BLE001
        # LLM/tool lỗi giữa chừng (vd 429 rate-limit OpenRouter, network...) — KHÔNG
        # được để lộ ra ngoài rồi bị `_on_message` nuốt im lặng (hành vi trước đây):
        # turn sẽ treo vĩnh viễn — FE chờ SSE không bao giờ tới, `assistant` message
        # kẹt `status="queued"` trong Postgres mãi mãi. Coi như turn "done" với nội
        # dung báo lỗi thay vì thêm 1 trạng thái mới (`status="error"` phải sửa cả
        # DTO/FE/DB enum) — người dùng vẫn thấy phản hồi, có thể hỏi lại ngay.
        print(f"[Agent Worker] lỗi khi chạy turn {req.message_id}: {exc}")
        error_text = (
            "Xin lỗi, hệ thống gặp sự cố khi xử lý câu hỏi này (có thể do quá tải "
            "tạm thời). Vui lòng thử lại sau ít phút."
        )
        await _emit(channel, {"type": "message.done", "content": error_text, **base})
        await redis_publish(channel, STREAM_DONE_SENTINEL)
        await rabbitmq_client.publish(
            AGENT_RESPONSE_QUEUE,
            AgentResponseMessage(
                conversation_id=req.conversation_id,
                message_id=req.message_id,
                content=error_text,
                status="done",
                # Suy luận đã tích luỹ được TRƯỚC KHI lỗi vẫn có giá trị xem lại (vd đã
                # gọi được vài tool trước khi LLM 429) — không bỏ phí.
                reasoning=context.reasoning_steps or None,
            ).model_dump_json().encode("utf-8"),
        )
        return

    if interrupt is not None:
        await _handle_interrupt(channel, base, req, interrupt, context)
        return

    answer = final_message.text if final_message is not None else ""
    await _emit(channel, {"type": "message.done", "content": answer, **base})
    await redis_publish(channel, STREAM_DONE_SENTINEL)
    await rabbitmq_client.publish(
        AGENT_RESPONSE_QUEUE,
        AgentResponseMessage(
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            content=answer,
            status="done",
            reasoning=context.reasoning_steps or None,
        ).model_dump_json().encode("utf-8"),
    )


async def _handle_interrupt(
    channel: str,
    base: dict[str, Any],
    req: TurnRequest,
    interrupt: Interrupt,
    context: AgentContext,
) -> None:
    """Turn tạm dừng ở tool `ask_user` (`app/agent/tools.py`) — payload `interrupt.value`
    là `{"question": ..., "options": [...]}` do tool tự truyền, `interrupt.id` (LangGraph
    tự sinh, ổn định cho ĐÚNG lần dừng này) dùng làm `questionId` cho FE (`POST
    .../questions/{questionId}/answer`, `docs/api-doc.md` mục 2.2)."""
    payload = interrupt.value if isinstance(interrupt.value, dict) else {}
    choice = MessageChoiceDto(
        question_id=interrupt.id,
        question=str(payload.get("question", "")),
        options=[
            ChoiceOptionDto(id=f"opt-{i}", label=str(label))
            for i, label in enumerate(payload.get("options") or [])
        ],
    )
    choice_json = choice.model_dump(mode="json", by_alias=True)

    await _emit(channel, {"type": "message.question", "choice": choice_json, **base})
    await redis_publish(channel, STREAM_DONE_SENTINEL)
    await rabbitmq_client.publish(
        AGENT_RESPONSE_QUEUE,
        AgentResponseMessage(
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            content="",
            status="question",
            choice=choice_json,
            reasoning=context.reasoning_steps or None,
        ).model_dump_json().encode("utf-8"),
    )


def _human_message_content(req: TurnRequest) -> str:
    """Nối thêm object key MinIO của ảnh đính kèm (nếu có) vào cuối nội dung tin nhắn —
    agent đọc thấy `object_key` này trong `messages` rồi tự copy làm tham số khi gọi
    `classify_skin_image` (`app/agent/tools/skin_image_classifier.py`, hướng dẫn ở
    `SYSTEM_PROMPT`, `graph.py`). Không có cơ chế multimodal content riêng ở tầng
    `create_agent` hiện tại nên forward bằng text là cách đơn giản nhất, nhất quán với
    cách LLM orchestrate mọi tool khác (đọc context -> tự chọn tham số gọi tool)."""
    content = req.content or ""
    images = [a for a in (req.attachments or []) if a.type.startswith("image/")]
    if not images:
        return content

    lines = [f'- name="{a.name}" object_key="{a.object_key}"' for a in images]
    return content + "\n\n[Ảnh đính kèm]\n" + "\n".join(lines)


async def _handle_turn(req: TurnRequest) -> None:
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=req.conversation_id)
    if req.is_steer:
        await _emit(
            channel,
            {
                "type": "message.steered",
                "corrId": req.corr_id,
                "conversationId": req.conversation_id,
                "messageId": req.message_id,
                "content": req.content,
            },
        )
    await _drive(req, {"messages": [HumanMessage(content=_human_message_content(req))]})


async def _handle_resume(req: TurnRequest) -> None:
    await _drive(req, Command(resume=req.answer))


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            req = TurnRequest.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"[Agent Worker] invalid message: {exc}")
            return

        async with _conversation_locks[req.conversation_id]:
            try:
                if req.type == "resume":
                    await _handle_resume(req)
                else:
                    await _handle_turn(req)
            except Exception as exc:  # noqa: BLE001
                print(f"[Agent Worker] error: {exc}")


async def main() -> None:
    log_startup_infra()
    print(f"[Agent Worker] model: {settings.AGENT_MODEL}")
    await rabbitmq_client.connect()
    print(f"[Agent Worker] listening on '{AGENT_REQUEST_QUEUE}'...")
    await rabbitmq_client.consume(AGENT_REQUEST_QUEUE, _on_message)
    await asyncio.Event().wait()  # chạy tới khi bị dừng (Ctrl+C)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Agent Worker] stopped.")
