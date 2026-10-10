"""Business logic cho Message"""

from fastapi import UploadFile

from agent.dto.schemas import TurnAttachment, TurnRequest
from app.common.constant import MessageSender, MessageType
from app.config.settings import settings
from app.config.constants import (
    AGENT_ACTIVE_TURN_KEY,
    AGENT_PENDING_TURN_KEY,
    AGENT_REQUEST_QUEUE,
)
from app.dto.common import FileDto
from app.dto.request.message import MessageAnswerDto, SendMessageInput
from app.dto.response.message import MessageMetadataDto, MessageOutput, SendMessageResult
from app.infra.rabbitmq_client import RabbitMQClient
from app.infra.redis_client import RedisClient
from app.models.file import File
from app.models.message import Message
from app.models.video_call import VideoCall
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.file_repository import FileRepository
from app.repositories.message_repository import MessageRepository
from app.services.file_store_service import FileStoreService


class MessageNotFoundError(Exception):
    """Không tìm thấy assistant message đang chờ đúng `question_id` (mục 2.2)."""


class TurnInProgressError(Exception):
    """Hội thoại đang có turn chạy (hoặc chờ trả lời `ask_user`) — đã bỏ Steer nên không nhận tin mới lúc này."""


class AttachmentNotFoundError(Exception):
    """Tệp đính kèm gửi kèm tin nhắn chưa được upload qua `POST /uploads` (không có trong `files`)."""


class MessageService:
    def __init__(
        self,
        message_repository: MessageRepository,
        conversation_repository: ConversationRepository,
        file_repository: FileRepository,
        file_store: FileStoreService,
        redis: RedisClient,
    ) -> None:
        self._messages = message_repository
        self._conversations = conversation_repository
        self._files = file_repository
        self._file_store = file_store  # bucket ảnh đính kèm
        self._redis = redis

    async def upload_attachment(self, upload: UploadFile) -> FileDto:
        stored = await self._file_store.save_upload(upload)
        row = await self._files.create(
            File(file_name=stored["name"], storage_key=stored["id"], content_type=stored["type"], size=stored["size"])
        )
        return self._file_dto(row)

    def _file_dto(self, f: File) -> FileDto:
        return FileDto(file_name=f.file_name, storage_key=f.storage_key, content_type=f.content_type, size=f.size,
                       created_at=f.created_at.isoformat(), url=self._file_store.presigned_url(f.storage_key))

    async def _resolve_attachments(self, body: SendMessageInput) -> list[File]:
        keys = [f.storage_key for f in body.attached_files or []]
        if not keys:
            return []
        found = await self._files.by_storage_keys(keys)
        missing = [k for k in keys if k not in found]
        if missing:
            raise AttachmentNotFoundError(", ".join(missing))
        return [found[k] for k in keys]

    async def _create_user_message(self, conversation_id: str, content: str, files: list[File]) -> Message:
        message = Message(
            conversation_id=conversation_id,
            sender=MessageSender.PATIENT.value,
            message_type=(MessageType.ATTACHED if files else MessageType.TEXT).value,
            content=content,
            status="done",
        )
        await self._messages.create(message)
        if files:
            await self._files.attach_to_message(message.id, files)
        return message

    def _to_output(
        self, message: Message, files: list[File] | None = None, video_call: VideoCall | None = None
    ) -> MessageOutput:
        # `message_type` là cột riêng (để lọc), `attached_files` ở `message_files`, `video_call` ở `video_calls`; trên wire
        # cả ba nằm trong `metadata` như base `MessageMetadata`
        metadata = MessageMetadataDto.model_validate(
            {**(message.extra or {}), "message_type": message.message_type,
             "attached_files": [self._file_dto(f).model_dump() for f in files] if files else None,
             "video_call": {"room_id": video_call.room_id, "status": video_call.status,
                            "started_at": video_call.started_at, "ended_at": video_call.ended_at} if video_call else None}
        )
        return MessageOutput(
            id=message.id,
            conversation_id=message.conversation_id,
            sender=MessageSender(message.sender),
            content=message.content,
            status=message.status,  # type: ignore[arg-type]
            metadata=metadata,
            created_at=message.created_at.isoformat(),
        )

    async def _apply_model_choice(
        self, conversation_id: str, model_id: str | None
    ) -> None:
        if not model_id or model_id not in settings.AGENT_MODEL_CHOICES:
            return
        conversation = await self._conversations.get(conversation_id)
        if conversation is not None and conversation.model != model_id:
            await self._conversations.update_model(conversation, model_id)

    async def list_messages(self, conversation_id: str) -> list[MessageOutput]:
        messages = await self._messages.list_by_conversation(conversation_id)
        files = await self._files.for_messages([m.id for m in messages])
        calls = await self._messages.video_calls(messages)
        return [
            self._to_output(m, files.get(m.id), calls.get(m.video_call_id) if m.video_call_id else None)
            for m in messages
        ]

    async def start_new_turn(
        self,
        *,
        conversation_id: str,
        content: str,
        attached_files: list[File] | None = None,
        corr_id: str | None = None,
        model_id: str | None = None,
    ) -> tuple[Message, Message]:
        """Mở 1 turn mới"""
        await self._apply_model_choice(conversation_id, model_id)

        user_message = await self._create_user_message(conversation_id, content, attached_files or [])

        assistant_message = Message(
            conversation_id=conversation_id,
            sender=MessageSender.AI.value,
            content="",
            status="queued",
            extra={"reasoning": []},
        )
        await self._messages.create(assistant_message)

        await self._redis.set_value(
            AGENT_ACTIVE_TURN_KEY.format(conversation_id=conversation_id),
            assistant_message.id,
            ex_seconds=settings.AGENT_TURN_KEY_TTL,
        )
        await self._defer_turn(
            conversation_id,
            TurnRequest(
                type="turn",
                conversation_id=conversation_id,
                message_id=assistant_message.id,
                corr_id=corr_id,
                content=content,
                attached_files=_turn_attachments(attached_files or []),
            ),
        )
        return user_message, assistant_message

    async def send_message(
        self, conversation_id: str, body: SendMessageInput
    ) -> SendMessageResult:
        active_turn_id = await self._redis.get(
            AGENT_ACTIVE_TURN_KEY.format(conversation_id=conversation_id)
        )
        if active_turn_id is not None:
            raise TurnInProgressError(active_turn_id)

        files = await self._resolve_attachments(body)
        user_message, assistant_message = await self.start_new_turn(
            conversation_id=conversation_id,
            content=body.content,
            attached_files=files,
            corr_id=body.client_message_id,
            model_id=body.model_id,
        )
        return SendMessageResult(
            user_message=self._to_output(user_message, files),
            assistant_message=self._to_output(assistant_message),
        )

    async def answer_question(
        self, conversation_id: str, question_id: str, body: MessageAnswerDto
    ) -> MessageOutput:
        message = await self._messages.find_pending_by_question_id(
            conversation_id, question_id
        )
        if message is None:
            raise MessageNotFoundError(question_id)

        await self._defer_turn(
            conversation_id,
            TurnRequest(
                type="resume",
                conversation_id=conversation_id,
                message_id=message.id,
                # Resume gửi TEXT thuần cho tool `ask_user` (`agent/tools/ask_user.py`) —
                # không còn 1 DTO chờ/resume riêng như bản Turn/Step/Reasoning cũ,
                # `question_id` chỉ dùng để Core tìm ĐÚNG message đang chờ ở trên, không
                # cần forward tiếp cho Worker (1 hội thoại chỉ có ĐÚNG 1 câu hỏi đang
                # chờ tại 1 thời điểm).
                answer=body.label or body.option_id,
            ),
        )
        return self._to_output(message)

    async def _defer_turn(self, conversation_id: str, req: TurnRequest) -> None:
        """Lưu `TurnRequest` chờ flush (handler SSE publish sau khi subscribe)."""
        await self._redis.set_value(
            AGENT_PENDING_TURN_KEY.format(conversation_id=conversation_id),
            req.model_dump_json(),
            ex_seconds=settings.AGENT_TURN_KEY_TTL,
        )


async def flush_pending_turn(conversation_id: str, redis: RedisClient, rabbitmq: RabbitMQClient) -> None:
    """Đẩy `TurnRequest` đang chờ"""
    key = AGENT_PENDING_TURN_KEY.format(conversation_id=conversation_id)
    payload = await redis.get_del(key)
    if not payload:
        return
    try:
        await rabbitmq.publish(
            AGENT_REQUEST_QUEUE, payload.encode("utf-8")
        )
    except Exception:
        # Publish hỏng SAU khi đã GETDEL — trả `payload` lại Redis để lần mở SSE kế tiếp
        # (client tự reconnect) thử lại, tránh mất turn / assistant row kẹt "queued".
        await redis.set_value(key, payload, ex_seconds=settings.AGENT_TURN_KEY_TTL)
        raise


def _turn_attachments(files: list[File]) -> list[TurnAttachment] | None:
    """Chỉ forward attachment ẢNH cho Worker"""
    images = [f for f in files if (f.content_type or "").startswith("image/")]
    if not images:
        return None
    return [
        TurnAttachment(file_name=f.file_name, content_type=f.content_type or "", storage_key=f.storage_key)
        for f in images
    ]
