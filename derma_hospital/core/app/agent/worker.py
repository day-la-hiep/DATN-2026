"""Agent worker — tiến trình riêng, tách khỏi FastAPI process.

Luồng (xem `docs/async-api-doc.md`, `kien-truc-agent.md`):
  1. consume  RabbitMQ  `agent_request_queue`  (Core đẩy turn mới / resume)
  2. Nạp long-term memory liên quan (semantic search Qdrant theo `user_id`) làm
     context đầu turn mới, xem `app/agent/memory.py`/`kien-truc-memory.md`.
  3. chạy     LangGraph (`app/agent/graph.py`), publish từng Reasoning lên Redis
     `agent:events:{conversation_id}` theo thời gian thực (`kien-truc-he-thong.md` mục 3)
  4. Khi turn tạm dừng (`status="question"`) hoặc kết thúc (`status="done"`), publish
     `AgentResponseMessage` vào RabbitMQ `agent_response_queue` — Worker KHÔNG đụng
     Postgres (trừ ĐỌC, xem `_load_memory_context`), Core là consumer duy nhất làm
     upsert (`docs/async-api-doc.md` mục 6, `app/agent/response_consumer.py`).
  5. Khi turn kết thúc thành công, tóm tắt (distill) turn đó thành 1 memory mới,
     lưu vào Qdrant (`app/agent/memory.py::distill_and_store`).

Chạy:  cd core && python -m app.agent.worker
"""
import asyncio
import json
from typing import Any

from aio_pika.abc import AbstractIncomingMessage
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.agent import memory
from app.agent.graph import agent_graph
from app.agent.schemas import AgentResponseMessage, TurnRequest
from app.agent.state import ReasoningResult, TurnState
from app.core.constants import (
    AGENT_EVENTS_CHANNEL,
    AGENT_REQUEST_QUEUE,
    AGENT_RESPONSE_QUEUE,
    STREAM_DONE_SENTINEL,
)
from app.db.session import AsyncSessionLocal
from app.infra import qdrant_client
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import publish as redis_publish
from app.repositories.conversation_repository import ConversationRepository

# Số ký tự mỗi lần `*.delta` khi KHÔNG có token thật để stream — dùng cho reasoning
# `tool_call`/`tool_ask` (`_publish_reasoning`, nội dung có sẵn ngay, không qua LLM) và
# đoạn `message.delta` lặp lại `final_answer` cuối turn (đã stream thật ở
# `reasoning.step_delta` rồi, đây chỉ echo lại). Reasoning "gọi LLM" stream token thật
# qua `get_stream_writer()` (`app/agent/graph.py::_run_llm`), không dùng hằng số này.
DELTA_CHUNK_SIZE = 24


async def _emit(channel: str, payload: dict[str, Any]) -> None:
    await redis_publish(channel, json.dumps(payload))


def _all_reasoning(state: TurnState) -> list[ReasoningResult]:
    results: list[ReasoningResult] = []
    for step in state["steps"]:
        results.extend(step.reasoning)
    results.extend(state["current_step"])
    return results


async def _publish_reasoning(
    channel: str, message_id: str, conversation_id: str, r: ReasoningResult
) -> None:
    base: dict[str, Any] = {
        "messageId": message_id,
        "conversationId": conversation_id,
        "stepId": r.step_id,
    }
    # by_alias=True: `MessageChoiceDto` là CamelModel (`app/dto/message.py`) — publish thủ
    # công qua Redis KHÔNG đi qua FastAPI response serialization (vốn tự áp alias mặc
    # định), nên phải tự truyền `by_alias=True`, nếu không field sẽ ra snake_case
    # (`question_id`) thay vì `questionId` như FE (`MessageChoice`) và
    # `MessageRepository.find_pending_by_question_id` (tra raw dict) đang mong đợi.
    choice = {"choice": r.choice.model_dump(mode="json", by_alias=True)} if r.choice else {}

    await _emit(
        channel,
        {"type": "reasoning.step_started", "title": r.title, "stepType": r.step_type, **base, **choice},
    )
    for i in range(0, len(r.content), DELTA_CHUNK_SIZE):
        await _emit(
            channel,
            {"type": "reasoning.step_delta", "delta": r.content[i : i + DELTA_CHUNK_SIZE], **base},
        )
    await _emit(
        channel, {"type": "reasoning.step_completed", "stepType": r.step_type, **base, **choice}
    )


async def _persist_assistant(
    *, message_id: str, conversation_id: str, content: str, status: str, reasoning: list[ReasoningResult]
) -> None:
    """Publish `agent_response_queue` thay vì ghi DB trực tiếp — Core consume queue này
    và tự làm upsert (`app/agent/response_consumer.py`, `docs/async-api-doc.md` mục 6)."""
    msg = AgentResponseMessage(
        type="assistant_upsert",
        conversation_id=conversation_id,
        message_id=message_id,
        content=content,
        status=status,  # type: ignore[arg-type]
        # `to_dto()` map đúng shape `ReasoningStepDto` (id/status/type) — `extra.reasoning`
        # được `MessageMetadataDto` validate lại khi `GET /messages`, dump thẳng
        # `ReasoningResult` (step_id/step_type/step_continues) sẽ lỗi thiếu field.
        reasoning=[r.to_dto().model_dump(mode="json", by_alias=True) for r in reasoning],
    )
    await rabbitmq_client.publish(AGENT_RESPONSE_QUEUE, msg.model_dump_json().encode("utf-8"))


async def _drive_graph(req: TurnRequest, input_or_command: object, published: set[str]) -> None:
    """Chạy graph tới khi kết thúc turn HOẶC tạm dừng (`interrupt`); publish Redis +
    persist DB theo diễn biến. Dùng chung cho turn mới lẫn resume."""
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=req.conversation_id)
    config: RunnableConfig = {"configurable": {"thread_id": req.message_id}}

    last_state: TurnState | None = None
    interrupted = False

    # 2 stream mode cùng lúc: "values" (state đầy đủ sau mỗi node, như cũ) + "custom"
    # (token thật do `_run_llm()`/`get_stream_writer()` phát ra NGAY trong lúc node đang
    # chạy — xem `app/agent/graph.py`). Mỗi item yield ra là tuple `(mode, payload)`.
    async for mode, chunk in agent_graph.astream(
        input_or_command, config, stream_mode=["values", "custom"]
    ):
        if isinstance(chunk, dict) and "__interrupt__" in chunk:
            interrupted = True
            break

        if mode == "custom":
            # `chunk` đã đúng shape wire event sẵn từ graph.py — forward gần như nguyên
            # văn, không cần map tên riêng.
            await _emit(channel, chunk)
            if chunk.get("type") == "reasoning.step_completed":
                # Đánh dấu đã publish để vòng lặp "values" bên dưới (dùng cho reasoning
                # tool_call/tool_ask — không stream qua "custom") không publish lại.
                published.add(chunk["stepId"])
            continue

        state: TurnState = chunk  # type: ignore[assignment]
        last_state = state

        for steer_content in state.get("last_steer_batch") or []:
            await _emit(
                channel,
                {
                    "type": "message.steered",
                    "corrId": req.corr_id,
                    "conversationId": req.conversation_id,
                    "messageId": req.message_id,
                    "content": steer_content,
                },
            )

        for r in _all_reasoning(state):
            if r.step_id not in published:
                await _publish_reasoning(channel, req.message_id, req.conversation_id, r)
                published.add(r.step_id)

    if last_state is None:
        print(f"[Agent Worker] error: graph không sinh state nào cho {req.message_id}")
        return

    if interrupted:
        await _persist_assistant(
            message_id=req.message_id,
            conversation_id=req.conversation_id,
            content="",
            status="question",
            reasoning=_all_reasoning(last_state),
        )
        await redis_publish(channel, STREAM_DONE_SENTINEL)
        return

    answer = last_state["final_answer"] or ""
    for i in range(0, len(answer), DELTA_CHUNK_SIZE):
        await _emit(
            channel,
            {
                "type": "message.delta",
                "messageId": req.message_id,
                "conversationId": req.conversation_id,
                "delta": answer[i : i + DELTA_CHUNK_SIZE],
            },
        )

    reasoning = _all_reasoning(last_state)
    await _emit(
        channel,
        {
            "type": "message.done",
            "messageId": req.message_id,
            "conversationId": req.conversation_id,
            # `to_dto()` — xem giải thích ở `_persist_assistant` (shape ReasoningStepDto,
            # khớp FE `ReasoningStep{id,status,type}` thay vì state nội bộ step_id/step_type).
            "reasoning": [r.to_dto().model_dump(mode="json", by_alias=True) for r in reasoning],
        },
    )
    await redis_publish(channel, STREAM_DONE_SENTINEL)

    await _persist_assistant(
        message_id=req.message_id,
        conversation_id=req.conversation_id,
        content=answer,
        status="done",
        reasoning=reasoning,
    )
    # Xoá Redis active-turn key: chuyển sang `response_consumer.py` (Core) — Core là bên
    # đã SET key này lúc publish turn nên để Core tự dọn khi đã persist xong DB là đối
    # xứng, và tránh 1 khoảng race nhỏ (key bị xoá trước khi DB thật sự ghi xong).

    # Long-term memory: tóm tắt turn vừa xong + lưu Qdrant (không chặn turn nếu lỗi —
    # `memory.distill_and_store` tự nuốt exception). CHỈ distill khi turn thật sự
    # xong (nhánh này), KHÔNG distill turn đang tạm dừng chờ `ask_user` (nhánh
    # `interrupted` ở trên) vì turn đó chưa hoàn tất.
    async with AsyncSessionLocal() as db:
        conversation = await ConversationRepository(db).get(req.conversation_id)
    if conversation is not None:
        # Lấy nội dung câu hỏi GỐC từ `HumanMessage` đầu tiên trong state, KHÔNG dùng
        # `req.content` trực tiếp — khi turn được resume (`_handle_resume`), `req` là
        # request loại "resume" có `content=None` (nội dung gốc nằm ở request ĐẦU).
        user_content = next(
            (m.content for m in last_state["messages"] if isinstance(m, HumanMessage)), ""
        )
        await memory.distill_and_store(
            user_id=conversation.user_id,
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            user_content=str(user_content),
            reasoning=reasoning,
            answer=answer,
        )


async def _load_memory_context(conversation_id: str, query_text: str) -> str | None:
    """Semantic search long-term memory liên quan `query_text` theo `user_id` của
    conversation — đọc Postgres trực tiếp (READ, không phải WRITE, vẫn đúng nguyên
    tắc "Core là writer duy nhất" — xem tiền lệ `pre_step`'s `list_pending_steers`)."""
    async with AsyncSessionLocal() as db:
        conversation = await ConversationRepository(db).get(conversation_id)
    if conversation is None:
        return None
    return await memory.retrieve_context(user_id=conversation.user_id, query_text=query_text)


async def _initial_state(req: TurnRequest) -> TurnState:
    memory_context = await _load_memory_context(req.conversation_id, req.content or "")
    messages: list[HumanMessage | SystemMessage] = []
    if memory_context:
        messages.append(SystemMessage(content=memory_context))
    messages.append(HumanMessage(content=req.content or ""))
    return {
        "conversation_id": req.conversation_id,
        "message_id": req.message_id,
        "messages": messages,
        "steps": [],
        "current_step": [],
        "step_count": 0,
        "just_closed_step": False,
        "outcome": None,
        "final_answer": None,
        "pending_tool": None,
        "last_steer_batch": [],
    }


async def _published_from_snapshot(config: RunnableConfig) -> set[str]:
    """Seed tập step_id đã publish từ checkpoint hiện có — tránh phát lại các Reasoning
    đã stream ở lần chạy trước khi resume (mỗi resume là 1 lần gọi `_on_message` riêng,
    không chia sẻ biến `published` trong bộ nhớ với lần chạy trước)."""
    snapshot = agent_graph.get_state(config)
    if not snapshot.values:
        return set()
    state: TurnState = snapshot.values  # type: ignore[assignment]
    return {r.step_id for r in _all_reasoning(state)}


async def _handle_turn(req: TurnRequest) -> None:
    if req.is_steer:
        # Steer được `pre_step` của turn ĐANG CHẠY tự đọc từ DB (list_pending_steers) —
        # không cần (và không nên) khởi động 1 lần astream() riêng cho cùng thread_id.
        # Giới hạn đã biết: nếu turn gốc vừa kết thúc đúng lúc Steer này tới, Steer sẽ
        # bị bỏ lỡ — chưa xử lý race này ở bản base.
        print(f"[Agent Worker] steer nhận, chờ pre_step của turn {req.message_id} đọc DB")
        return

    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=req.conversation_id)
    await _emit(
        channel,
        {
            "type": "message.started",
            "corrId": req.corr_id,
            "conversationId": req.conversation_id,
            "messageId": req.message_id,
        },
    )
    await _drive_graph(req, await _initial_state(req), published=set())


async def _handle_resume(req: TurnRequest) -> None:
    config: RunnableConfig = {"configurable": {"thread_id": req.message_id}}
    published = await _published_from_snapshot(config)
    await _drive_graph(req, Command(resume=req.answer), published)


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
            req = TurnRequest.model_validate(payload)
            if req.type == "resume":
                await _handle_resume(req)
            else:
                await _handle_turn(req)
        except Exception as exc:  # noqa: BLE001
            print(f"[Agent Worker] error: {exc}")


async def main() -> None:
    await qdrant_client.ensure_collection()
    await rabbitmq_client.connect()
    print(f"[Agent Worker] listening on '{AGENT_REQUEST_QUEUE}'...")
    await rabbitmq_client.consume(AGENT_REQUEST_QUEUE, _on_message)
    await asyncio.Event().wait()  # chạy tới khi bị dừng (Ctrl+C)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Agent Worker] stopped.")
