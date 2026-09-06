"""Router Conversation + Message — REST (`docs/api-doc.md`) và SSE (`docs/async-api-doc.md`)."""
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_conversation_service, get_message_service
from app.core.constants import AGENT_EVENTS_CHANNEL, STREAM_DONE_SENTINEL
from app.dto.common import ApiResponse
from app.dto.conversation import ConversationOutput, CreateConversationInput
from app.dto.message import MessageAnswerDto, MessageOutput, SendMessageInput
from app.infra.redis_client import subscribe
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageNotFoundError, MessageService

router = APIRouter(tags=["conversations"])

ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationOutput]],
    operation_id="listConversations",
)
async def list_conversations(
    service: ConversationServiceDep,
    user_id: Annotated[str, Query(alias="userId")],
) -> ApiResponse[list[ConversationOutput]]:
    """`docs/api-doc.md` mục 1.1. Auth chưa có — `userId` truyền tay (mục 0)."""
    conversations = await service.list_conversations(user_id)
    return ApiResponse(data=conversations)


@router.post(
    "/conversations",
    status_code=201,
    response_model=ApiResponse[ConversationOutput],
    operation_id="createConversation",
)
async def create_conversation(
    body: CreateConversationInput, service: ConversationServiceDep
) -> ApiResponse[ConversationOutput]:
    """`docs/api-doc.md` mục 1.2 — tạo hội thoại + lưu `initMessage` + publish turn đầu."""
    conversation = await service.create_conversation(body)
    return ApiResponse(data=conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[list[MessageOutput]],
    operation_id="listMessages",
)
async def list_messages(
    conversation_id: str, service: MessageServiceDep
) -> ApiResponse[list[MessageOutput]]:
    """`docs/api-doc.md` mục 1.3 — sắp theo `createdAt` tăng dần."""
    messages = await service.list_messages(conversation_id)
    return ApiResponse(data=messages)


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=202,
    response_model=ApiResponse[MessageOutput],
    operation_id="sendMessage",
)
async def send_message(
    conversation_id: str, body: SendMessageInput, service: MessageServiceDep
) -> ApiResponse[MessageOutput]:
    """`docs/api-doc.md` mục 2.1 — tin nhắn mở đầu turn mới HOẶC Steer (không dùng để
    trả lời câu hỏi agent đang chờ, xem `answer_question` bên dưới)."""
    message = await service.send_message(conversation_id, body)
    return ApiResponse(data=message)


@router.post(
    "/conversations/{conversation_id}/questions/{question_id}/answer",
    status_code=202,
    response_model=ApiResponse[MessageOutput],
    operation_id="answerQuestion",
)
async def answer_question(
    conversation_id: str,
    question_id: str,
    body: MessageAnswerDto,
    service: MessageServiceDep,
) -> ApiResponse[MessageOutput]:
    """`docs/api-doc.md` mục 2.2 — trả lời `tool_ask` đang chờ, KHÔNG tạo `messages` mới."""
    try:
        message = await service.answer_question(conversation_id, question_id, body)
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy câu hỏi đang chờ trả lời."
        ) from exc
    return ApiResponse(data=message)


async def _sse_event_stream(conversation_id: str) -> AsyncIterator[str]:
    """Forward nguyên văn từng message từ Redis Pub/Sub ra SSE — Core là pure forwarder,
    không transform (`docs/async-api-doc.md` mục 1)."""
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=conversation_id)
    async for message in subscribe(channel):
        data = message["data"]
        yield f"data: {data}\n\n"
        if data == STREAM_DONE_SENTINEL:
            break


@router.get("/conversations/{conversation_id}/stream", include_in_schema=False)
async def stream_conversation(conversation_id: str) -> StreamingResponse:
    """`docs/async-api-doc.md` mục 1 — SSE, đóng khi nhận sentinel `[DONE]`.

    `include_in_schema=False`: SSE thuộc phạm vi `docs/asyncapi.yaml`, không lặp lại
    trong `docs/openapi.yaml` (OpenAPI mô tả REST request/response thông thường).
    """
    return StreamingResponse(
        _sse_event_stream(conversation_id), media_type="text/event-stream"
    )
