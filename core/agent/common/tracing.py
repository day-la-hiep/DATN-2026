"""Log vòng lặp graph"""
import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

logger = logging.getLogger("agent.trace")

_PREVIEW = 160
# Node nội bộ của `create_agent` ("model", "tools") và của chat graph; các chain con khác (RunnableSequence...) bị bỏ qua cho đỡ ồn.
_SKIP_NODES = {"__start__", "__end__"}
# `interrupt()` của `ask_user` bay lên qua tool dưới dạng exception — đó là tạm dừng chờ người dùng, không phải lỗi.
_PAUSE_EXCEPTIONS = {"GraphInterrupt", "GraphBubbleUp", "NodeInterrupt"}


def _preview(value: Any) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= _PREVIEW else text[: _PREVIEW - 1] + "…"


def _model_name(serialized: dict[str, Any] | None, metadata: dict[str, Any] | None) -> str:
    if metadata and metadata.get("ls_model_name"):
        return str(metadata["ls_model_name"])
    return str((serialized or {}).get("name") or "llm")


class TraceCallback(AsyncCallbackHandler):
    # Phải chạy cùng task với graph để contextvar (`request_id`) còn nguyên trong dòng log.
    run_inline = True

    def __init__(self) -> None:
        self._starts: dict[UUID, float] = {}

    def _begin(self, run_id: UUID) -> None:
        self._starts[run_id] = time.perf_counter()

    def _elapsed(self, run_id: UUID) -> str:
        start = self._starts.pop(run_id, None)
        return f"{time.perf_counter() - start:.2f}s" if start is not None else "?"

    # ---- node của graph ----
    async def on_chain_start(self, serialized: dict[str, Any] | None, inputs: Any, *, run_id: UUID, name: str | None = None,
                             metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        node = (metadata or {}).get("langgraph_node")
        if node and name == node and node not in _SKIP_NODES:
            self._begin(run_id)
            logger.info("NODE ▶ %s", node)

    async def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        if run_id in self._starts:
            logger.info("NODE ◀ %s", self._elapsed(run_id))

    async def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        if run_id in self._starts:
            elapsed = self._elapsed(run_id)
            if type(error).__name__ in _PAUSE_EXCEPTIONS:
                logger.info("NODE ⏸ tạm dừng chờ người dùng (%s)", elapsed)
            else:
                logger.error("NODE ✖ %s: %s (%s)", type(error).__name__, error, elapsed)

    # ---- LLM ----
    async def on_chat_model_start(self, serialized: dict[str, Any] | None, messages: list[list[Any]], *, run_id: UUID,
                                  metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self._begin(run_id)
        logger.info("LLM  ▶ %s (%d tin nhắn trong ngữ cảnh)", _model_name(serialized, metadata), len(messages[0]) if messages else 0)

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        gen = response.generations[0][0] if response.generations and response.generations[0] else None
        message = gen.message if isinstance(gen, ChatGeneration) else None
        parts = [self._elapsed(run_id)]
        if isinstance(message, AIMessage):
            usage = message.usage_metadata
            if usage:
                parts.append(f"token in={usage.get('input_tokens', '?')} out={usage.get('output_tokens', '?')}")
            if message.tool_calls:
                parts.append("tool_calls=" + ",".join(c["name"] for c in message.tool_calls))
            else:
                logger.debug("LLM  trả lời: %s", _preview(message.text))
        logger.info("LLM  ◀ %s", " | ".join(parts))

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        logger.error("LLM  ✖ %s: %s (%s)", type(error).__name__, _preview(error), self._elapsed(run_id))

    # ---- tool ----
    async def on_tool_start(self, serialized: dict[str, Any] | None, input_str: str, *, run_id: UUID,
                            inputs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self._begin(run_id)
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        logger.info("TOOL ▶ %s %s", name, _preview(inputs if inputs is not None else input_str))

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        content = getattr(output, "content", output)
        logger.info("TOOL ◀ %s | %s", self._elapsed(run_id), _preview(content))

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        elapsed = self._elapsed(run_id)
        if type(error).__name__ in _PAUSE_EXCEPTIONS:
            logger.info("TOOL ⏸ chờ người dùng trả lời (%s)", elapsed)
        else:
            logger.warning("TOOL ✖ %s: %s (%s)", type(error).__name__, _preview(error), elapsed)


# Một instance dùng chung: trạng thái chỉ là bảng run_id -> thời điểm bắt đầu, mỗi run_id duy nhất.
trace_callback = TraceCallback()
