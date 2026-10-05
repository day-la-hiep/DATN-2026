"""Xử lý 1 turn của agent: dựng `AgentContext`, chạy `agent_graph.astream()`, forward token
thật lên Redis và kết thúc turn (xong / hỏi lại qua `ask_user` / lỗi).

`thread_id` (checkpointer) = `conversation_id` — 1 hội thoại = 1 thread, mọi turn nối tiếp qua
`messages` (`agent/graph/chat_graph.py::config_for`). `message.thinking`/`message.tool_result`
được middleware phát trực tiếp trong lúc graph chạy (`agent/middleware/`), KHÔNG phải từ vòng
lặp `astream()` ở đây — vòng lặp này chỉ forward token (`message.delta`) và tóm kết quả cuối.
"""

from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command, Interrupt

from agent.dto.schemas import TurnRequest
from agent.graph.chat_graph import agent_graph, config_for
from agent.state.context import AgentContext
from agent.handler.publisher import emit, finish_turn
from app.config.settings import settings
from app.config.constants import AGENT_EVENTS_CHANNEL
from app.api.deps import get_postgres_client
from app.dto.response.message import ChoiceOptionDto, MessageChoiceDto
from app.repositories.conversation_repository import ConversationRepository

_ERROR_TEXT = (
    "Xin lỗi, hệ thống gặp sự cố khi xử lý câu hỏi này (có thể do quá tải "
    "tạm thời). Vui lòng thử lại sau ít phút."
)


async def _conversation_for(conversation_id: str) -> tuple[str, str]:
    """`(user_id, model)` — `model` đã resolve từ id ngắn (`Conversation.model`) sang
    chuỗi "provider:model" thật qua `AGENT_MODEL_CHOICES` (`app/config/settings.py`). Id
    rỗng/không còn trong `AGENT_MODEL_CHOICES` (model bị gỡ khỏi danh sách sau khi
    conversation đã chọn) -> trả rỗng, `AgentContext.model` rỗng -> middleware
    `select_model` tự fallback `settings.AGENT_MODEL`."""
    async with get_postgres_client().session_factory() as db:
        repo = ConversationRepository(db)
        conversation = await repo.get(conversation_id)
        if conversation is None:
            return "", ""
        user_id = await repo.owner_user_id(conversation) or ""
    model = settings.AGENT_MODEL_CHOICES.get(conversation.model, "")
    return user_id, model


async def _build_context(req: TurnRequest) -> AgentContext:
    user_id, model = await _conversation_for(req.conversation_id)
    return AgentContext(
        user_id=user_id,
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        image_keys=[
            a.storage_key
            for a in (req.attached_files or [])
            if a.content_type.startswith("image/")
        ],
        model=model,
    )


def _human_message_content(req: TurnRequest) -> str:
    """Nối thêm object key MinIO của ảnh đính kèm (nếu có) vào cuối nội dung tin nhắn —
    agent đọc thấy `object_key` này trong `messages` rồi tự copy làm tham số khi gọi
    `classify_skin_image` (`agent/tools/skin_image_classifier.py`, hướng dẫn ở
    `SYSTEM_PROMPT`). Không có cơ chế multimodal content riêng ở tầng `create_agent`
    hiện tại nên forward bằng text là cách đơn giản nhất, nhất quán với cách LLM
    orchestrate mọi tool khác (đọc context -> tự chọn tham số gọi tool)."""
    content = req.content or ""
    images = [a for a in (req.attached_files or []) if a.content_type.startswith("image/")]
    if not images:
        return content

    # nhãn `object_key` giữ nguyên: là tên tham số của tool `classify_skin_image` mà prompt hướng dẫn LLM chép lại
    lines = [f'- name="{a.file_name}" object_key="{a.storage_key}"' for a in images]
    return content + "\n\n[Ảnh đính kèm]\n" + "\n".join(lines)


async def _stream_graph(
    input_: object,
    channel: str,
    base: dict[str, Any],
    context: AgentContext,
    req: TurnRequest,
) -> tuple[AIMessage | None, Interrupt | None]:
    """Chạy graph, forward token; trả `(AIMessage cuối, Interrupt nếu tạm dừng)`."""
    interrupt: Interrupt | None = None
    final_message: AIMessage | None = None

    async for mode, chunk in agent_graph.astream(  # pyright: ignore[reportUnknownMemberType]
        input_,
        config=config_for(req.conversation_id),
        context=context,
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            msg, meta = cast("tuple[Any, dict[str, Any]]", chunk)
            assert isinstance(msg, BaseMessage)
            # `langgraph_node == "model"` lọc đúng token của LLM chính — bỏ qua các lần
            # gọi model nội bộ khác (vd `SummarizationMiddleware` tự gọi LLM tóm tắt khi
            # vượt ngưỡng), không lẫn vào stream trả lời user.
            if meta.get("langgraph_node") == "model" and msg.text:
                await emit(
                    channel,
                    {"type": "message.delta", "delta": msg.text, **base},
                )
            continue

        # mode == "updates": state diff sau mỗi node — dùng để phát hiện interrupt (tool
        # `ask_user`) và tóm `AIMessage` cuối cùng (LangGraph đã gộp sẵn khi node "model"
        # hoàn tất, không cần tự cộng dồn từng chunk).
        update = cast(dict[str, Any], chunk)
        if "__interrupt__" in update:
            interrupt = cast(tuple[Interrupt, ...], update["__interrupt__"])[0]
            break
        model_update = update.get("model")
        if model_update:
            final_message = cast(AIMessage, model_update["messages"][-1])

    return final_message, interrupt


async def _finish_with_question(
    channel: str,
    base: dict[str, Any],
    req: TurnRequest,
    interrupt: Interrupt,
    context: AgentContext,
) -> None:
    """Turn tạm dừng ở tool `ask_user` — payload `interrupt.value` là `{"question": ...,
    "options": [...]}` do tool tự truyền, `interrupt.id` (LangGraph tự sinh, ổn định cho
    ĐÚNG lần dừng này) dùng làm `question_id` cho FE (`POST
    .../questions/{question_id}/answer`, `docs/api-doc.md` mục 2.2)."""
    raw: Any = interrupt.value
    payload: dict[str, Any] = (
        cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    )
    choice = MessageChoiceDto(
        question_id=interrupt.id,
        question=str(payload.get("question", "")),
        options=[
            ChoiceOptionDto(id=f"opt-{i}", label=str(label))
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
    context = await _build_context(req)
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
        # LLM/tool lỗi giữa chừng (vd 429 rate-limit OpenRouter, network...) — KHÔNG được
        # để lộ ra ngoài rồi bị `on_message` nuốt im lặng: turn sẽ treo vĩnh viễn — FE chờ
        # SSE không bao giờ tới, `assistant` message kẹt `status="queued"` trong Postgres.
        # Coi như turn "done" với nội dung báo lỗi thay vì thêm 1 trạng thái mới
        # (`status="error"` phải sửa cả DTO/FE/DB enum) — người dùng vẫn thấy phản hồi,
        # có thể hỏi lại ngay. Suy luận đã tích luỹ TRƯỚC KHI lỗi vẫn có giá trị xem lại.
        print(f"[Agent Worker] lỗi khi chạy turn {req.message_id}: {exc}")
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
