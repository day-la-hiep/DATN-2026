import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from agent.graph.common import TOOL_DISPLAY_NAMES, emit
from agent.context.agent_context import AgentContext
from agent.tools.reasoning import STAGE_LABELS, TOOL_NAME as REASONING_TOOL

logger = logging.getLogger(__name__)


@wrap_tool_call
async def emit_tool_result(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
) -> ToolMessage | Command[Any]:
    """Publish `message.tool_result` lên Redis SAU khi tool thực thi xong"""
    try:
        response = await handler(request)
    except GraphBubbleUp:
        raise
    except Exception as exc:  # noqa: BLE001
        # Trả ToolMessage lỗi thay vì ném: AIMessage(tool_calls) đã nằm trong checkpoint,
        # thiếu ToolMessage đi sau thì turn kế tiếp bị provider từ chối (400) và hội thoại kẹt.
        tool_name = (
            request.tool.name
            if request.tool
            else request.tool_call.get("name", "")
        )
        logger.warning("tool '%s' lỗi: %s", tool_name, exc)
        response = ToolMessage(
            content=f"Lỗi khi gọi công cụ '{tool_name}': {exc}",
            name=tool_name,
            tool_call_id=request.tool_call.get("id", ""),
        )

    ctx: AgentContext = request.runtime.context  # type: ignore[assignment]
    if ctx.conversation_id and isinstance(response, ToolMessage):
        tool_name = response.name or request.tool_call.get("name", "")
        display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)

        # id khớp scheme FE (`fe/features/chat/store.ts`): cùng tên hiển thị thì ghi đè step cũ.
        tool_args = (
            request.tool_call.get("args")
            if isinstance(request.tool_call, dict)
            else None
        )
        # Mỗi `stage` của record_reasoning cần tên riêng, nếu không dedupe theo tên sẽ ghi đè lập luận đầu.
        if tool_name == REASONING_TOOL and isinstance(tool_args, dict):
            display_name = STAGE_LABELS.get(str(tool_args.get("stage")), display_name)
        step_id = f"{ctx.message_id}-tool-{display_name}"
        step = {
            "id": step_id,
            "title": f"Gọi tool: {display_name}",
            "input": tool_args,
            "content": str(response.content),
            "status": "done",
            "type": "tool",
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
                "conversation_id": ctx.conversation_id,
                "message_id": ctx.message_id,
            },
        )
    return response
