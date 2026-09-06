"""Business logic cho Message — gửi tin nhắn (turn mới/Steer), trả lời câu hỏi
(`tool_ask`), liệt kê tin nhắn. Xem `docs/api-doc.md` mục 2, `docs/async-api-doc.md`
mục 4–6.
"""
import json

from app.agent.schemas import TurnRequest
from app.core.constants import (
    AGENT_ACTIVE_TURN_KEY,
    AGENT_EVENTS_CHANNEL,
    AGENT_REQUEST_QUEUE,
)
from app.core.ids import new_message_id
from app.dto.message import (
    MessageAnswerDto,
    MessageMetadataDto,
    MessageOutput,
    SendMessageInput,
)
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import get as redis_get
from app.infra.redis_client import publish as redis_publish
from app.infra.redis_client import set_value as redis_set
from app.models.message import Message
from app.repositories.message_repository import MessageRepository


class MessageNotFoundError(Exception):
    """Không tìm thấy assistant message đang chờ đúng `questionId` (mục 2.2)."""


class MessageService:
    def __init__(self, message_repository: MessageRepository) -> None:
        self._messages = message_repository

    async def list_messages(self, conversation_id: str) -> list[MessageOutput]:
        messages = await self._messages.list_by_conversation(conversation_id)
        return [_to_output(m) for m in messages]

    async def start_new_turn(
        self,
        *,
        conversation_id: str,
        content: str,
        metadata: MessageMetadataDto | None = None,
        corr_id: str | None = None,
    ) -> Message:
        """Lưu tin nhắn mở đầu turn (`status="done"` ngay, mục 5 ghi chú cuối) + publish
        turn mới. Dùng cho `POST /conversations` (mục 1.2, quyết định thiết kế) và nhánh
        "không có turn đang chạy" của `send_message`."""
        user_message = Message(
            id=new_message_id(),
            conversation_id=conversation_id,
            role="user",
            content=content,
            status="done",
            extra=metadata.model_dump(mode="json", exclude_none=True)
            if metadata is not None
            else None,
        )
        await self._messages.create(user_message)

        assistant_message_id = new_message_id()
        await redis_set(
            AGENT_ACTIVE_TURN_KEY.format(conversation_id=conversation_id),
            assistant_message_id,
        )
        # `message.queued` — Core publish ngay khi đẩy request vào RabbitMQ, TRƯỚC khi
        # Agent Worker kịp nhận (Agent Worker tự publish `message.started` sau đó).
        await redis_publish(
            AGENT_EVENTS_CHANNEL.format(conversation_id=conversation_id),
            json.dumps(
                {
                    "type": "message.queued",
                    "corrId": corr_id,
                    "conversationId": conversation_id,
                    "messageId": assistant_message_id,
                }
            ),
        )
        await self._publish(
            TurnRequest(
                type="turn",
                conversation_id=conversation_id,
                message_id=assistant_message_id,
                corr_id=corr_id,
                content=content,
                is_steer=False,
            )
        )
        return user_message

    async def send_message(
        self, conversation_id: str, body: SendMessageInput
    ) -> MessageOutput:
        """`POST /conversations/{id}/messages` (mục 2.1) — turn mới hoặc Steer tuỳ có
        turn đang chạy hay không (Redis `AGENT_ACTIVE_TURN_KEY`)."""
        active_turn_id = await redis_get(
            AGENT_ACTIVE_TURN_KEY.format(conversation_id=conversation_id)
        )

        metadata = _metadata_from_input(body)

        if active_turn_id is None:
            # Không có turn nào đang chạy -> đây là tin nhắn mở đầu turn mới.
            user_message = await self.start_new_turn(
                conversation_id=conversation_id,
                content=body.content,
                metadata=metadata,
                corr_id=body.client_message_id,
            )
            return _to_output(user_message)

        # Có turn đang chạy -> Steer: status="pending" tới khi pre_step append (mục 5).
        user_message = Message(
            id=new_message_id(),
            conversation_id=conversation_id,
            role="user",
            content=body.content,
            status="pending",
            extra=metadata.model_dump(mode="json", exclude_none=True)
            if metadata is not None
            else None,
        )
        await self._messages.create(user_message)

        await self._publish(
            TurnRequest(
                type="turn",
                conversation_id=conversation_id,
                message_id=active_turn_id,
                corr_id=body.client_message_id,
                content=body.content,
                is_steer=True,
                steer_message_id=user_message.id,
            )
        )
        return _to_output(user_message)

    async def answer_question(
        self, conversation_id: str, question_id: str, body: MessageAnswerDto
    ) -> MessageOutput:
        """`POST /conversations/{id}/questions/{questionId}/answer` (mục 2.2) — publish
        "resume request", KHÔNG tạo `messages` row mới (mục 4)."""
        message = await self._messages.find_pending_by_question_id(
            conversation_id, question_id
        )
        if message is None:
            raise MessageNotFoundError(question_id)

        await self._publish(
            TurnRequest(
                type="resume",
                conversation_id=conversation_id,
                message_id=message.id,
                question_id=question_id,
                answer=body.model_dump(mode="json"),
            )
        )
        return _to_output(message)

    async def _publish(self, req: TurnRequest) -> None:
        await rabbitmq_client.publish(
            AGENT_REQUEST_QUEUE, req.model_dump_json().encode("utf-8")
        )


def _metadata_from_input(body: SendMessageInput) -> MessageMetadataDto | None:
    if body.attachments is None and body.selection is None:
        return None
    return MessageMetadataDto(attachments=body.attachments, selection_ref=body.selection)


def _to_output(message: Message) -> MessageOutput:
    metadata = (
        MessageMetadataDto.model_validate(message.extra) if message.extra else None
    )
    return MessageOutput(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        status=message.status,  # type: ignore[arg-type]
        metadata=metadata,
        created_at=message.created_at.isoformat(),
    )
