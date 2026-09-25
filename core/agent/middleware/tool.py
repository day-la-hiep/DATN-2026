from typing import Any, Awaitable, Callable

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from agent.graph.common import TOOL_DISPLAY_NAMES, emit
from agent.state.context import AgentContext


@wrap_tool_call
async def emit_tool_result(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    """Publish `message.tool_result` lên Redis SAU khi tool thực thi xong — thay thế
    hoàn toàn phần `tools_update` cũ trong `worker.py::_drive`, GIỮ NGUYÊN shape event
    (`type`/`tool`/`content`/`conversationId`/`messageId`) nên FE không cần đổi gì. Tool tự
    `interrupt()` (`ask_user`, `app/agent/tools/ask_user.py`) raise `GraphBubbleUp` ngay
    trong `handler()` — KHÔNG chạy tới dòng emit, turn tạm dừng và được xử lý riêng ở
    `worker.py::_handle_interrupt`, giống hành vi cũ (re-raise ngay, KHÔNG rơi vào nhánh
    bắt lỗi bên dưới).

    Lỗi THẬT của tool (Neo4j/Qdrant/MinIO sập, API rate-limit...) — `ToolNode` mặc định
    của `create_agent` CHỈ tự bắt `ToolInvocationError` (sai tham số), còn lỗi runtime từ
    BÊN TRONG tool (vd `query_dermatology_kg` mất kết nối Neo4j) bị ném thẳng lên
    `agent_graph.astream()`, `worker.py::_drive` bắt ở tầng NGOÀI CÙNG rồi coi cả TURN là
    lỗi — nhưng KHÔNG rollback checkpoint: `AIMessage(tool_calls=[...])` đã bị
    `create_agent` ghi vào state TRƯỚC KHI tool này chạy vẫn còn trong lịch sử, không có
    `ToolMessage` nào theo sau. Turn SAU đó (checkpointer nối tiếp `messages`, xem
    `config_for`) gửi nguyên lịch sử này cho LLM -> nhiều provider (đã gặp thật với
    DeepSeek) từ chối cứng: "assistant message with 'tool_calls' must be followed by
    tool messages" (400), hội thoại kẹt vĩnh viễn từ đó về sau. Bắt lỗi NGAY TẠI ĐÂY,
    trả về `ToolMessage` báo lỗi thay vì để lộ exception — giữ checkpoint hợp lệ (mọi
    `tool_calls` luôn có `ToolMessage` theo sau), model tự đọc lỗi và có thể thử cách
    khác/báo người dùng thay vì cả turn treo."""
    try:
        response = await handler(request)
    except GraphBubbleUp:
        raise
    except Exception as exc:  # noqa: BLE001
        tool_name = (
            request.tool.name
            if request.tool
            else request.tool_call.get("name", "")
        )
        print(f"[Agent Graph] tool '{tool_name}' lỗi: {exc}")
        response = ToolMessage(
            content=f"Lỗi khi gọi công cụ '{tool_name}': {exc}",
            name=tool_name,
            tool_call_id=request.tool_call.get("id", ""),
        )

    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    if ctx.conversation_id and isinstance(response, ToolMessage):
        tool_name = response.name or request.tool_call.get("name", "")
        display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)

        # id khớp scheme FE tự sinh khi nhận `message.tool_result` trực tiếp
        # (`fe/features/chat/store.ts`) — GHI ĐÈ (không append) nếu CÙNG tool đã gọi
        # trước đó trong turn, đúng hành vi live (dedup theo tên tool hiển thị, không
        # phân biệt tham số khác nhau — hạn chế đã có từ trước, không phải lỗi mới).
        tool_args = (
            request.tool_call.get("args")
            if isinstance(request.tool_call, dict)
            else None
        )
        step_id = f"{ctx.message_id}-tool-{display_name}"
        step = {
            "id": step_id,
            "title": f"Gọi tool: {display_name}",
            "input": tool_args,
            "content": str(response.content),
            "status": "done",
            "type": "tool_call",
        }
        existing_index = next(
            (
                i
                for i, s in enumerate(ctx.reasoning_steps)
                if s["id"] == step_id
            ),
            None,
        )
        if existing_index is not None:
            ctx.reasoning_steps[existing_index] = step
        else:
            ctx.reasoning_steps.append(step)

        await emit(
            ctx.conversation_id,
            {
                "type": "message.tool_result",
                "tool": display_name,
                "input": tool_args,
                "content": response.content,
                "conversationId": ctx.conversation_id,
                "messageId": ctx.message_id,
            },
        )
    return response
