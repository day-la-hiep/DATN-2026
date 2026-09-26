import re
from typing import Any, Awaitable, Callable
from langchain.agents import AgentState
from langchain.agents.middleware import (
    ModelRequest,
    ModelResponse,
    Runtime,
    after_model,
    wrap_model_call,
)
from langchain.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages import RemoveMessage

from agent.graph.common import (
    MAX_CRITIC_RETRIES,
    MAX_REASONING_RETRIES,
    THINKING_SUMMARY_MAX_LEN,
    THINKING_TITLE_RE,
    TOOL_DISPLAY_NAMES,
    CriticState,
    CriticVerdict,
    emit,
)
from agent.llm import get_model
from agent.prompt.critic import CRITIC_SYSTEM
from agent.prompt.orchestrator import SYSTEM_PROMPT
from agent.state.context import AgentContext
from agent.tools.memory import search_memories
from agent.tools.reasoning import (
    FEEDBACK_PREFIX,
    TOOL_NAME as REASONING_TOOL,
    analyze_turn,
    needs_reasoning,
    turn_messages,
)


@wrap_model_call
async def select_model(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """Chọn model theo `AgentContext.model` (đã resolve sẵn thành "provider:model" ở
    `worker.py`) thay cho model mặc định `create_agent()` được khởi tạo cùng — PHẢI đứng
    ĐẦU danh sách middleware (`build_agent_graph`) để mọi middleware sau (vd
    `inject_long_term_memory`) thấy đúng model đã chọn qua `request.model`."""
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    if ctx.model:
        request = request.override(model=get_model(ctx.model))
    return await handler(request)


@wrap_model_call
async def inject_long_term_memory(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """Semantic search long-term memory liên quan tin nhắn user gần nhất rồi chèn vào
    `system_message` TRƯỚC mỗi lần gọi LLM — nhớ chủ động, không cần agent tự hỏi lại
    (`app/agent/memory.py::search_memories`)."""
    messages = request.state["messages"]
    query = next(
        (
            str(m.content)
            for m in reversed(messages)
            if isinstance(m, HumanMessage)
        ),
        "",
    )
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    memories = await search_memories(request.runtime.store, ctx.user_id, query)  # type: ignore[arg-type]

    if memories:
        memory_text = "\n".join(f"- {m}" for m in memories)
        base = (
            request.system_message.content
            if request.system_message
            else SYSTEM_PROMPT
        )
        request = request.override(
            system_message=SystemMessage(
                content=f"{base}\n\nThông tin đã biết về người dùng:\n{memory_text}"
            )
        )
    return await handler(request)


@wrap_model_call
async def emit_reasoning_step(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """Publish `message.thinking` lên Redis SAU MỖI lần gọi LLM trong vòng lặp ReAct
    (không chỉ lần cuối) — không đổi hành vi model, chỉ quan sát `response.result` rồi
    forward tiếp. Có "thinking" block thật từ provider (Gemini, `include_thoughts=True`)
    -> tóm tắt như cũ. KHÔNG có (đa số model qua OpenRouter hiện dùng,
    `app/core/config.py::AGENT_MODEL`) nhưng model vừa quyết định gọi tool -> tự tổng hợp
    1 dòng từ `TOOL_DISPLAY_NAMES` thay vì im lặng bỏ qua như bản cũ (`worker.py::_drive`
    trước đây chỉ emit khi có reasoning block) — cho người dùng thấy được bước suy luận dù
    provider không hỗ trợ "thinking" riêng. Không có cả 2 (vd lượt trả lời cuối, nội dung
    đã đi qua `message.delta`) -> không emit gì thêm."""
    response = await handler(request)

    ai_message = next(
        (m for m in response.result if isinstance(m, AIMessage)), None
    )
    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    if ai_message is None or not ctx.conversation_id:
        return response

    reasoning = "".join(
        block.get("reasoning", "")
        for block in ai_message.content_blocks
        if block.get("type") == "reasoning"
    ).strip()

    if reasoning:
        content = _summarize_thinking(reasoning)
    elif ai_message.tool_calls:
        names = [
            TOOL_DISPLAY_NAMES.get(tc["name"], tc["name"])
            for tc in ai_message.tool_calls
        ]
        content = f"Đang thực hiện: {', '.join(names)}"
    else:
        return response

    # id khớp CHÍNH XÁC scheme FE tự sinh lúc nhận event trực tiếp (KHÔNG qua persist,
    # `fe/features/chat/store.ts` case `"message.thinking"`) — `len(...)` tại đây =
    # `list.length` bên FE tại thời điểm nhận event vì 2 bên cùng tăng theo ĐÚNG 1 thứ tự
    # sự kiện (chỉ khác nơi tích luỹ). Khớp id để FE không tạo trùng bước khi
    # `GET .../messages` (dùng list persist) ghi đè lên list đang stream dở.
    ctx.reasoning_steps.append(
        {
            "id": f"{ctx.message_id}-thinking-{len(ctx.reasoning_steps)}",
            "title": content,
            "content": content,
            "status": "done",
            "type": "thinking",
        }
    )
    await emit(
        ctx.conversation_id,
        {
            "type": "message.thinking",
            "content": content,
            "conversationId": ctx.conversation_id,
            "messageId": ctx.message_id,
        },
    )
    return response


@after_model(can_jump_to=["model"], state_schema=CriticState)
async def critic_review(
    state: CriticState, runtime: Runtime[AgentContext]
) -> dict[str, Any] | None:
    """Chạy SAU mỗi lần model trả lời. Bản nháp CÓ `tool_calls` (còn đang tra cứu, chưa
    phải câu trả lời cuối) → bỏ qua, để routing mặc định sang node "tools" như bình
    thường. Turn KHÔNG có `ToolMessage` nào (chào hỏi/ngoài phạm vi, mục 2 SYSTEM_PROMPT
    — không tra cứu gì) → cũng bỏ qua, chạy critic chỉ tốn thêm 1 lệnh gọi LLM vô ích vì
    không có gì để đối chiếu.

    Từ chối → chèn feedback dạng `HumanMessage` (đánh dấu rõ nguồn gốc nội bộ, không
    phải lời người dùng thật) rồi `jump_to="model"` bắt model trả lời lại CÓ tính tới
    feedback. Giới hạn `MAX_CRITIC_RETRIES` lần/turn — hết lượt vẫn bị từ chối thì CHO
    QUA (chấp nhận câu trả lời còn rủi ro thay vì treo turn vô thời hạn); LangSmith vẫn
    ghi lại verdict cuối để review sau."""
    messages = state["messages"]
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or last.tool_calls:
        return None
    if not any(isinstance(m, ToolMessage) for m in messages):
        return None

    retries = state.get("critic_retries", 0)
    if retries >= MAX_CRITIC_RETRIES:
        return None

    ctx: AgentContext = runtime.context  # type: ignore[assignment]
    if ctx.conversation_id:
        await emit(
            ctx.conversation_id,
            {
                "type": "message.thinking",
                "content": "Đang kiểm duyệt câu trả lời trước khi gửi",
                "conversationId": ctx.conversation_id,
                "messageId": ctx.message_id,
            },
        )

    critic_model = get_model().with_structured_output(
        CriticVerdict, method="function_calling"
    )
    verdict = await critic_model.ainvoke(
        [SystemMessage(content=CRITIC_SYSTEM), *messages]
    )
    assert isinstance(verdict, CriticVerdict)

    if ctx.conversation_id:
        await emit(
            ctx.conversation_id,
            {
                "type": "message.tool_result",
                "tool": "Kiểm duyệt câu trả lời",
                "content": "Đạt yêu cầu."
                if verdict.approved
                else f"Cần viết lại: {verdict.feedback}",
                "conversationId": ctx.conversation_id,
                "messageId": ctx.message_id,
            },
        )

    if verdict.approved:
        return None

    feedback_message = HumanMessage(
        content=(
            "[Hệ thống kiểm duyệt — không phải lời người dùng] Câu trả lời vừa rồi cần "
            f"chỉnh lại trước khi gửi: {verdict.feedback}. Hãy trả lời lại, khắc phục "
            "đúng điều trên, dựa trên dữ liệu tool đã có (không cần gọi lại tool trừ khi "
            "thật sự thiếu dữ liệu)."
        )
    )
    return {
        "messages": [feedback_message],
        "critic_retries": retries + 1,
        "jump_to": "model",
    }


def _summarize_thinking(text: str) -> str:
    first_block = text.strip().split("\n\n", 1)[0].strip()
    title_match = THINKING_TITLE_RE.match(first_block)
    summary = title_match.group(1).strip() if title_match else first_block
    # Không có tiêu đề in đậm (fallback) -> cắt ở câu đầu tiên thay vì cả đoạn.
    if not title_match:
        summary = re.split(r"(?<=[.!?])\s", summary, maxsplit=1)[0]
    if len(summary) > THINKING_SUMMARY_MAX_LEN:
        summary = summary[: THINKING_SUMMARY_MAX_LEN - 1].rstrip() + "…"
    return summary


@wrap_model_call
async def force_reasoning(
    request: ModelRequest[AgentContext],
    handler: Callable[[ModelRequest[AgentContext]], Awaitable[ModelResponse]],
) -> ModelResponse:
    """Ngay SAU 1 đợt kết quả tool (message cuối là `ToolMessage`) mà chưa có lần lập luận hợp
    lệ nào MỚI HƠN bằng chứng đó -> ÉP model gọi `record_reasoning` (chỉ bind đúng tool này +
    `tool_choice` chỉ định tên) thay vì để nó tự chọn. Ép TRƯỚC khi model sinh chữ nên không có
    bản nháp nào lọt ra stream `message.delta` (khác chặn sau bằng `after_model`, xem
    `enforce_initial_reasoning`). `record_reasoning` trả "Không hợp lệ" -> ép lại, tối đa
    `MAX_REASONING_RETRIES` lần rồi thả tự do. Provider bỏ qua `tool_choice` -> model có thể
    vẫn trả lời chữ; `enforce_initial_reasoning` là lưới an toàn cho trường hợp đó."""
    messages = request.state["messages"]
    if messages and isinstance(messages[-1], ToolMessage):
        state = analyze_turn(turn_messages(messages))
        if state.pending_evidence and state.invalid_count < MAX_REASONING_RETRIES:
            request = request.override(
                tools=[t for t in request.tools if getattr(t, "name", None) == REASONING_TOOL],
                tool_choice={"type": "function", "function": {"name": REASONING_TOOL}},
            )
    return await handler(request)


@after_model(can_jump_to=["model"])
async def enforce_initial_reasoning(
    state: AgentState[Any], runtime: Runtime[AgentContext]
) -> dict[str, Any] | None:
    """Lưới an toàn sau mỗi lần model trả lời (`force_reasoning` không phủ được các trường
    hợp này):
      - R1: model gọi tool tra cứu mà chưa lập luận (lần đầu của turn, hoặc còn bằng chứng
        mới chưa được lập luận vì provider bỏ qua `tool_choice`) và không kèm `record_reasoning`
        hợp lệ trong cùng lượt gọi -> bỏ `AIMessage` đó (`RemoveMessage`, tránh `tool_calls` mồ
        côi không có `ToolMessage`) và bắt làm lại. Tool call không có chữ nên chưa có gì lọt ra
        `message.delta`.
      - R2: model trả lời bằng chữ dù còn bằng chứng chưa được lập luận (provider bỏ qua
        `tool_choice`) -> bắt viết lại; bản nháp CÓ thể đã stream ra (giới hạn đã biết, giống
        `critic_review`), nên chỉ là phương án dự phòng.
      - R3: phản hồi rỗng (không chữ, không tool call) -> bắt làm lại.
    Lượt chào hỏi/ngoài phạm vi (không tool, không bằng chứng) không bị ép. Hết
    `MAX_REASONING_RETRIES` thì cho qua."""
    messages = state["messages"]
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage):
        return None

    turn = analyze_turn(turn_messages(messages[:-1]))
    if turn.feedback_count >= MAX_REASONING_RETRIES:
        return None

    if last.tool_calls:
        if last.id is None or not needs_reasoning(last):
            return None
        stage_hint = (
            'stage="initial": nêu dữ kiện đã biết (kèm nguồn) và giả thuyết ban đầu'
            if not turn.has_valid_reasoning
            else 'stage="after_evidence" (hoặc "final"): cập nhật giả thuyết theo kết quả tool '
            "vừa nhận"
        )
        if turn.has_valid_reasoning and not turn.pending_evidence:
            return None
        return {
            "messages": [
                RemoveMessage(id=last.id),
                HumanMessage(
                    content=(
                        f"{FEEDBACK_PREFIX} Trước khi gọi thêm tool, hãy gọi `{REASONING_TOOL}` "
                        f"với {stage_hint}. Sau đó mới tiếp tục tra cứu."
                    )
                ),
            ],
            "jump_to": "model",
        }

    if not last.text.strip():
        # Phản hồi rỗng (không chữ, không tool call) — provider thỉnh thoảng trả về; không thể
        # để người dùng nhận câu trả lời trống.
        return {
            "messages": [
                RemoveMessage(id=last.id) if last.id else HumanMessage(content="."),
                HumanMessage(
                    content=(
                        f"{FEEDBACK_PREFIX} Phản hồi vừa rồi rỗng. Hãy tiếp tục: gọi tool cần "
                        "thiết hoặc trả lời người dùng."
                    )
                ),
            ],
            "jump_to": "model",
        }

    if turn.pending_evidence:
        return {
            "messages": [
                HumanMessage(
                    content=(
                        f"{FEEDBACK_PREFIX} Bạn vừa nhận kết quả tool nhưng chưa lập luận. Hãy "
                        f'gọi `{REASONING_TOOL}` (stage="after_evidence" hoặc "final") để cập '
                        "nhật giả thuyết theo bằng chứng, rồi mới trả lời."
                    )
                )
            ],
            "jump_to": "model",
        }
    return None
