"""Router Conversation + Message — REST (`docs/api-doc.md`) và SSE (`docs/async-api-doc.md`)."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_conversation_service,
    get_current_user,
    get_message_service,
    get_rabbitmq_client,
    get_redis_client,
)
from app.config.settings import settings
from app.config.constants import AGENT_EVENTS_CHANNEL, STREAM_DONE_SENTINEL
from app.dto.common import ApiResponse
from app.dto.request.conversation import CreateConversationInput, UpdateConversationModelInput
from app.dto.request.message import MessageAnswerDto, SendMessageInput
from app.dto.response.conversation import ConversationOutput, ModelOption
from app.dto.response.message import MessageOutput, SendMessageResult
from app.infra.rabbitmq_client import RabbitMQClient
from app.models.user import User
from app.infra.redis_client import RedisClient
from app.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
    PatientProfileNotFoundError,
)
from app.services.message_service import (
    AttachmentNotFoundError,
    MessageNotFoundError,
    MessageService,
    TurnInProgressError,
    flush_pending_turn,
)

router = APIRouter(tags=["conversations"])

ConversationServiceDep = Annotated[
    ConversationService, Depends(get_conversation_service)
]
MessageServiceDep = Annotated[MessageService, Depends(get_message_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/models",
    response_model=ApiResponse[list[ModelOption]],
    operation_id="listModelOptions",
)
async def list_model_options() -> ApiResponse[list[ModelOption]]:
    """Danh sách model FE cho user chọn lúc tạo/đổi hội thoại"""
    return ApiResponse(
        data=[
            ModelOption(id=model_id)
            for model_id in settings.AGENT_MODEL_CHOICES
        ]
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationOutput]],
    operation_id="listConversations",
)
async def list_conversations(
    service: ConversationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[list[ConversationOutput]]:
    """`docs/api-doc.md` mục 1.1 — luôn theo tài khoản trong JWT, không nhận `user_id` từ client."""
    conversations = await service.list_conversations(current_user.id)
    return ApiResponse(data=conversations)


@router.post(
    "/conversations",
    status_code=201,
    response_model=ApiResponse[ConversationOutput],
    operation_id="createConversation",
)
async def create_conversation(
    body: CreateConversationInput,
    service: ConversationServiceDep,
    current_user: CurrentUserDep,
) -> ApiResponse[ConversationOutput]:
    """`docs/api-doc.md` mục 1.2 — tạo hội thoại + lưu `content` + publish turn đầu."""
    try:
        # chủ hội thoại luôn là tài khoản đăng nhập, bỏ qua `user_id` client gửi
        conversation = await service.create_conversation(body.model_copy(update={"user_id": current_user.id}))
    except PatientProfileNotFoundError as exc:
        raise HTTPException(
            status_code=400, detail="Tài khoản chưa có hồ sơ bệnh nhân."
        ) from exc
    return ApiResponse(data=conversation)


@router.patch(
    "/conversations/{conversation_id}/model",
    response_model=ApiResponse[ConversationOutput],
    operation_id="updateConversationModel",
)
async def update_conversation_model(
    conversation_id: str,
    body: UpdateConversationModelInput,
    service: ConversationServiceDep,
) -> ApiResponse[ConversationOutput]:
    """Đổi model cho hội thoại"""
    try:
        conversation = await service.update_model(conversation_id, body.model)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy hội thoại."
        ) from exc
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
    response_model=ApiResponse[SendMessageResult],
    operation_id="sendMessage",
)
async def send_message(
    conversation_id: str, body: SendMessageInput, service: MessageServiceDep
) -> ApiResponse[SendMessageResult]:
    """`docs/api-doc.md` mục 2.1"""
    try:
        result = await service.send_message(conversation_id, body)
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=400, detail=f"Tệp đính kèm chưa được tải lên: {exc}"
        ) from exc
    except TurnInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail="Trợ lý đang trả lời hoặc đang chờ bạn trả lời câu hỏi, vui lòng đợi.",
        ) from exc
    return ApiResponse(data=result)


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
        message = await service.answer_question(
            conversation_id, question_id, body
        )
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy câu hỏi đang chờ trả lời."
        ) from exc
    return ApiResponse(data=message)


async def _sse_event_stream(redis: RedisClient, rabbitmq: RabbitMQClient, conversation_id: str) -> AsyncIterator[str]:
    """Forward nguyên văn từng message từ Redis Pub/Sub ra SSE"""
    channel = AGENT_EVENTS_CHANNEL.format(conversation_id=conversation_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        await flush_pending_turn(conversation_id, redis, rabbitmq)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            yield f"data: {data}\n\n"
            if data == STREAM_DONE_SENTINEL:
                break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


@router.get("/conversations/{conversation_id}/stream", include_in_schema=False)
async def stream_conversation(
    conversation_id: str,
    redis: Annotated[RedisClient, Depends(get_redis_client)],
    rabbitmq: Annotated[RabbitMQClient, Depends(get_rabbitmq_client)],
) -> StreamingResponse:
    """`docs/async-api-doc.md` mục 1"""
    return StreamingResponse(
        _sse_event_stream(redis, rabbitmq, conversation_id), media_type="text/event-stream"
    )
