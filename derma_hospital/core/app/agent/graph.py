"""LangGraph: Turn = pre_step ⇄ reasoning (lặp trong 1 Step) → finalize.

Đúng theo `kien-truc-agent.md`:
  - `pre_step`: quyết định tiếp tục (mở Step mới) hay kết thúc turn; append Steer đang
    chờ vào context nếu có (mục 5, `docs/async-api-doc.md` mục 5).
  - `reasoning`: **1 hành động duy nhất mỗi lần chạy** — HOẶC gọi LLM, HOẶC thực thi 1 tool
    mà lần gọi LLM ngay trước đó vừa yêu cầu (KHÔNG gộp 2 việc vào 1 lần, xem mục 0). Tự lặp
    lại chính nó khi còn việc phải làm trong Step. Tool tra theo tên trong registry
    (`app/agent/tools.TOOLS_BY_NAME`, KHÔNG hard-code tên tool cụ thể nào ở đây) — tool
    `requires_wait=True` (vd `ask_user`, hoặc tool khác cần đợi khá lâu/chờ callback bên
    ngoài) → sang `tool_wait`; tool thường thực thi luôn (có thể await lâu) rồi lặp lại
    `reasoning`. Gọi LLM mà không yêu cầu tool nào nữa → Step đóng lại, quay về `pre_step`.
  - `tool_wait`: node chờ TỔNG QUÁT cho mọi tool `requires_wait=True` — `interrupt()`, tạm
    dừng graph, chờ resume qua `POST .../questions/{questionId}/answer` (`docs/api-doc.md`
    mục 2.2) hoặc 1 kênh resume khác tương ứng tool đó.
  - `finalize`: chốt câu trả lời cuối.

Không có node `ask_question` riêng ở cấp Turn — hỏi user là 1 tool bên trong `reasoning`,
chỉ khác các tool khác ở chỗ `requires_wait=True` (xem `app/agent/tools/base.py`).

Thêm tool mới: xem `app/agent/tools/` (registry + hợp đồng `ToolSpec`) — không cần sửa
node nào ở đây.

Giới hạn đã biết: giả định LLM chỉ gọi **tối đa 1 tool** mỗi lần (ép qua system prompt) —
chưa xử lý trường hợp model gọi nhiều tool song song trong cùng 1 response.
"""
from typing import Unpack, Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCall
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.agent.llm import get_llm_with_tools
from app.agent.schemas import AgentResponseMessage
from app.agent.state import PendingTool, ReasoningResult, StepResult, TurnState
from app.agent.tools import ALL_TOOLS, TOOLS_BY_NAME
from app.core.config import settings
from app.core.constants import AGENT_RESPONSE_QUEUE
from app.db.session import AsyncSessionLocal
from app.infra.rabbitmq_client import rabbitmq_client
from app.repositories.message_repository import MessageRepository

SYSTEM_PROMPT = (
    "Bạn là trợ lý tư vấn da liễu, suy luận từng bước trước khi trả lời. "
    "Mỗi lượt chỉ được gọi TỐI ĐA 1 tool (không gọi song song nhiều tool). "
    "Nếu thiếu thông tin quan trọng, gọi tool `ask_user` để hỏi lại thay vì đoán. "
    "Khi đã đủ thông tin, trả lời trực tiếp (không gọi thêm tool nào)."
)


async def pre_step(state: TurnState) -> dict[str, object]:
    """Quyết định tiếp tục hay kết thúc turn; append Steer đang `pending` nếu có
    (`docs/async-api-doc.md` mục 5) — đây chính là "cần append thêm message mới không?"
    ở định nghĩa Pre-step (`kien-truc-agent.md` mục 1)."""
    if state["step_count"] >= settings.AGENT_MAX_REASONING_STEPS:
        return {"outcome": "answer", "last_steer_batch": []}

    # Đọc Steer đang chờ: vẫn đọc DB trực tiếp (không phải vấn đề ownership — Core không
    # ghi đè các row này trước khi pre_step đọc). Ghi status "queued" thì publish qua
    # `agent_response_queue` (mục B.3 kế hoạch) thay vì `update_status` trực tiếp — Core
    # là writer duy nhất của bảng `messages` (`docs/async-api-doc.md` mục 6).
    async with AsyncSessionLocal() as db:
        repo = MessageRepository(db)
        pending = await repo.list_pending_steers(state["conversation_id"])
        steer_messages: list[AnyMessage] = []
        for steer in pending:
            steer_messages.append(HumanMessage(content=steer.content))
            await rabbitmq_client.publish(
                AGENT_RESPONSE_QUEUE,
                AgentResponseMessage(
                    type="steer_status",
                    conversation_id=state["conversation_id"],
                    message_id=steer.id,
                    status="queued",
                ).model_dump_json().encode("utf-8"),
            )

    if steer_messages:
        return {
            "outcome": "continue",
            "current_step": [],
            "messages": steer_messages,
            "last_steer_batch": [m.content for m in steer_messages],  # type: ignore[misc]
        }

    if not state["steps"]:
        # Chưa chạy Step nào — bắt buộc phải có ít nhất 1 Step.
        return {"outcome": "continue", "current_step": [], "last_steer_batch": []}

    # Step gần nhất đã đóng lại mà không có Steer mới -> model đã trả lời xong.
    return {"outcome": "answer", "last_steer_batch": []}


def route_after_pre_step(state: TurnState) -> str:
    return "finalize" if state["outcome"] == "answer" else "reasoning"


def _pending_tool_call(state: TurnState) -> ToolCall | None:
    """Có tool nào vừa được LLM yêu cầu ở Reasoning ngay trước, còn chờ thực thi không?
    Nhận biết bằng: message cuối cùng là `AIMessage` có `tool_calls` (nếu đã thực thi rồi,
    message cuối sẽ là `ToolMessage`, không phải `AIMessage` nữa). Giả định chỉ 1 tool/lượt
    (xem system prompt) — chỉ lấy `tool_calls[0]`."""
    messages = state["messages"]
    if not messages:
        return None
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return last.tool_calls[0]
    return None


async def reasoning(state: TurnState) -> dict[str, object]:
    """Chạy ĐÚNG 1 Reasoning: nếu đang có tool chờ thực thi (từ lần gọi LLM ngay trước) thì
    thực thi tool đó; ngược lại gọi LLM. 2 việc này KHÔNG BAO GIỜ gộp chung 1 lần chạy."""
    pending_tool_call = _pending_tool_call(state)
    step_index = state["step_count"] + 1
    step_id = f"{state['message_id']}-step-{step_index}"

    if pending_tool_call is not None:
        return await _run_tool(state, step_id, step_index, pending_tool_call)
    return await _run_llm(state, step_id, step_index)


async def _run_llm(state: TurnState, step_id: str, step_index: int) -> dict[str, object]:
    """1 Reasoning kiểu "gọi LLM" — có thể quyết định gọi tool (Reasoning kế tiếp mới thực
    sự thực thi tool đó, xem `_run_tool`).

    Stream token thật qua `get_stream_writer()` — publish TRỰC TIẾP theo đúng shape wire
    event (`type`/`messageId`/`conversationId`/`stepId`/`delta`...) mà Redis event đã
    dùng, để `worker.py` chỉ cần forward gần như nguyên văn (`stream_mode=["values",
    "custom"]`, xem `_drive_graph`). `writer()` là no-op an toàn khi graph được drive với
    `stream_mode` không có `"custom"` — gọi vô điều kiện không ảnh hưởng chỗ khác đang
    chạy graph (vd script test/spike)."""
    writer = get_stream_writer()
    base: dict[str, object] = {
        "messageId": state["message_id"],
        "conversationId": state["conversation_id"],
        "stepId": step_id,
    }
    writer({"type": "reasoning.step_started", "title": "Suy luận", "stepType": "default", **base})

    llm = get_llm_with_tools(ALL_TOOLS)
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    full: AIMessageChunk | None = None
    try:
        async for chunk in llm.astream(messages):
            full = chunk if full is None else full + chunk  # type: ignore[assignment]
            # `.text` (property, KHÔNG phải `str(chunk.content)`) — 1 số provider (vd
            # Gemini qua `langchain-google-genai`) trả `content` dạng list content-block
            # (`[{"type": "text", "text": ...}]`), không phải string thuần; `str(...)` sẽ
            # in ra repr Python của list đó thay vì text thật. `.text` chuẩn hoá đúng cả
            # 2 dạng (string thuần lẫn list content-block).
            if chunk.text:
                writer({"type": "reasoning.step_delta", "delta": chunk.text, **base})
    except NotImplementedError:
        full = None  # provider/model không hỗ trợ streaming -> fallback dưới

    if full is None:
        response: AIMessage = await llm.ainvoke(messages)
        if response.text:
            writer({"type": "reasoning.step_delta", "delta": response.text, **base})
    else:
        # Chuẩn hoá AIMessageChunk về AIMessage thường trước khi đưa vào state/checkpoint.
        response = AIMessage(content=full.content, tool_calls=full.tool_calls)

    writer({"type": "reasoning.step_completed", "stepType": "default", **base})

    text = response.text
    step_continues = bool(getattr(response, "tool_calls", None))

    result = ReasoningResult(
        step_id=step_id,
        title="Suy luận",
        content=text or "(không có nội dung)",
        step_type="default",
        step_continues=step_continues,
    )

    if step_continues:
        return {
            "messages": [response],
            "current_step": [*state["current_step"], result],
            "step_count": step_index,
            "just_closed_step": False,
        }

    # Không yêu cầu tool nào -> đây là Reasoning cuối, Step đóng lại.
    closed_step = StepResult(reasoning=[*state["current_step"], result])
    return {
        "messages": [response],
        "steps": [*state["steps"], closed_step],
        "current_step": [],
        "step_count": step_index,
        "just_closed_step": True,
        "final_answer": text,
    }


async def _run_tool(
    state: TurnState, step_id: str, step_index: int, tool_call: ToolCall
) -> dict[str, object]:
    """1 Reasoning kiểu "thực thi tool" — tra `TOOLS_BY_NAME` theo tên, KHÔNG hard-code
    tên tool cụ thể nào (thêm tool mới không cần sửa hàm này, xem `app/agent/tools/`).
    Tool `requires_wait=True` không thực thi đồng bộ ở đây mà pause qua `tool_wait` (mục 3)."""
    spec = TOOLS_BY_NAME.get(tool_call["name"])

    if spec is None:
        # Tool chưa đăng ký trong registry — trả lỗi cho LLM tự xử lý ở lần gọi kế tiếp.
        content = f"Tool '{tool_call['name']}' chưa được hỗ trợ."
        tool_message = ToolMessage(content=content, tool_call_id=tool_call["id"])
        result = ReasoningResult(
            step_id=step_id,
            title=f"Gọi tool: {tool_call['name']}",
            content=content,
            step_type="tool_call",
            step_continues=True,
        )
        return {
            "messages": [tool_message],
            "current_step": [*state["current_step"], result],
            "step_count": step_index,
            "just_closed_step": False,
        }

    if spec.requires_wait:
        assert spec.build_wait_request is not None
        wait = spec.build_wait_request(tool_call, step_id)
        result = ReasoningResult(
            step_id=step_id,
            title=wait.title,
            content=wait.choice.question if wait.choice is not None else wait.title,
            step_type="tool_ask",
            choice=wait.choice,
            step_continues=True,
        )
        return {
            "current_step": [*state["current_step"], result],
            "step_count": step_index,
            "just_closed_step": False,
            "pending_tool": PendingTool(
                tool_call_id=tool_call["id"],
                tool_name=tool_call["name"],
                payload=wait.payload,
            ),
        }

    # Tool thực thi luôn, có thể `await` khá lâu (gọi API ngoài, tra cứu...) — không cần
    # interrupt() vì không cần input từ bên ngoài graph trong lúc chờ. Khi có tool thật
    # chạy lâu, có thể phát 1 event `reasoning.step_started` sớm ở đây (trước `spec.run`)
    # bằng đúng pattern `get_stream_writer()` của `_run_llm()`, để FE thấy spinner ngay
    # thay vì chờ tới lúc tool chạy xong mới thấy Reasoning xuất hiện.
    assert spec.run is not None
    content = await spec.run(tool_call)
    tool_message = ToolMessage(content=content, tool_call_id=tool_call["id"])
    result = ReasoningResult(
        step_id=step_id,
        title=f"Gọi tool: {tool_call['name']}",
        content=content,
        step_type="tool_call",
        step_continues=True,
    )
    return {
        "messages": [tool_message],
        "current_step": [*state["current_step"], result],
        "step_count": step_index,
        "just_closed_step": False,
    }


def route_after_reasoning(state: TurnState) -> str:
    if state.get("pending_tool") is not None:
        return "tool_wait"
    if state.get("just_closed_step"):
        return "pre_step"
    return "reasoning"


async def tool_wait(state: TurnState) -> dict[str, object]:
    """Node chờ TỔNG QUÁT cho MỌI tool `requires_wait=True` (không chỉ `ask_user`) —
    generic hoá `ask_user_wait` của bản trước. `interrupt()` là câu lệnh ĐẦU TIÊN — an
    toàn khi LangGraph re-run node này lúc resume (chỉ đọc lại `state`, không gọi lại
    LLM/tool nào, xem `kien-truc-agent.md` mục 3)."""
    pending = state["pending_tool"]
    assert pending is not None
    answer = interrupt(pending.payload)
    assert isinstance(answer, dict)

    spec = TOOLS_BY_NAME[pending.tool_name]
    assert spec.on_resume is not None
    resume_result = spec.on_resume(answer)
    tool_message = ToolMessage(
        content=resume_result.tool_message_content, tool_call_id=pending.tool_call_id
    )

    current_step = list(state["current_step"])
    if resume_result.answered is not None and current_step and current_step[-1].choice is not None:
        last = current_step[-1]
        current_step[-1] = last.model_copy(
            update={"choice": last.choice.model_copy(update={"answered": resume_result.answered})}
        )

    return {
        "messages": [tool_message],
        "current_step": current_step,
        "pending_tool": None,
        "just_closed_step": False,
    }


def finalize(state: TurnState) -> dict[str, object]:
    """Chốt câu trả lời. Nếu chạm giới hạn an toàn mà chưa có `final_answer`, dùng nội
    dung Reasoning gần nhất làm câu trả lời tạm."""
    if state["final_answer"] is not None:
        return {}
    if state["current_step"]:
        fallback = state["current_step"][-1].content
    elif state["steps"]:
        fallback = state["steps"][-1].reasoning[-1].content
    else:
        fallback = "Xin lỗi, tôi chưa có đủ thông tin để trả lời."
    return {"final_answer": fallback}


def build_agent_graph(
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph:
    graph = StateGraph(TurnState)

    graph.add_node("pre_step", pre_step)
    graph.add_node("reasoning", reasoning)
    graph.add_node("tool_wait", tool_wait)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "pre_step")
    graph.add_conditional_edges(
        "pre_step",
        route_after_pre_step,
        {"reasoning": "reasoning", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "reasoning",
        route_after_reasoning,
        {
            "tool_wait": "tool_wait",
            "pre_step": "pre_step",
            "reasoning": "reasoning",
        },
    )
    graph.add_edge("tool_wait", "reasoning")
    graph.add_edge("finalize", END)

    # InMemorySaver: đủ cho dev (worker chạy 1 process duy nhất). Production cần
    # checkpointer bền vững hơn tiến trình đơn — xem kien-truc-agent.md mục 3.
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


agent_graph = build_agent_graph()
