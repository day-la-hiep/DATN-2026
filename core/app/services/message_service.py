"""Business logic cho Message — gửi tin nhắn (turn mới/Steer), trả lời câu hỏi
(`tool_ask`), liệt kê tin nhắn. Xem `docs/api-doc.md` mục 2, `docs/async-api-doc.md`
mục 4–6.
"""
from app.agent.schemas import TurnAttachment, TurnRequest
from app.core.config import settings
from app.core.constants import (
    AGENT_ACTIVE_TURN_KEY,
    AGENT_PENDING_TURN_KEY,
    AGENT_REQUEST_QUEUE,
)
from app.core.ids import new_message_id
from app.dto.message import (
    MessageAnswerDto,
    MessageMetadataDto,
    MessageOutput,
    SendMessageInput,
    SendMessageResult,
)
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import get as redis_get
from app.infra.redis_client import get_del as redis_get_del
from app.infra.redis_client import set_value as redis_set
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository


class MessageNotFoundError(Exception):
    """Không tìm thấy assistant message đang chờ đúng `questionId` (mục 2.2)."""


class MessageService:
    def __init__(
        self,
        message_repository: MessageRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._messages = message_repository
        self._conversations = conversation_repository

    async def _apply_model_choice(self, conversation_id: str, model_id: str | None) -> None:
        """`SendMessageInput.model_id` (dropdown chọn model ở ô nhập chat, FE
        `features/chat/constants.ts::MODEL_OPTIONS`) — cập nhật LUÔN `Conversation.model`
        thay vì chỉ áp dụng 1 turn: model chọn theo TỪNG conversation (không phải riêng
        từng message), Worker resolve model MỚI NHẤT từ DB mỗi turn
        (`app/agent/worker.py::_conversation_for`) nên chỉ cần ghi đè cột này là turn kế
        tiếp (kể cả turn NGAY sau đây) tự dùng đúng model. id rỗng hoặc không nằm trong
        `AGENT_MODEL_CHOICES` (FE gửi id cũ/lỗi) -> bỏ qua thay vì lỗi cả lần gửi tin,
        giữ nguyên model hiện tại của hội thoại."""
        if not model_id or model_id not in settings.AGENT_MODEL_CHOICES:
            return
        conversation = await self._conversations.get(conversation_id)
        if conversation is not None and conversation.model != model_id:
            await self._conversations.update_model(conversation, model_id)

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
        model_id: str | None = None,
    ) -> tuple[Message, Message]:
        """Mở 1 turn mới — persist đủ 2 row NGAY, chưa đẩy Worker:

          1. user message (`status="done"`, mục 5 ghi chú cuối).
          2. assistant message của turn (`status="queued"`, `content=""`) — FE nhận `id`
             này ngay trong response `POST` để gắn vào bubble + lắng nghe SSE, không phải
             chờ event `message.started`.

        `TurnRequest` được lưu vào Redis `agent:pending_turn:*` thay vì publish thẳng —
        handler SSE (`GET .../stream`) `GETDEL` + publish sau khi `subscribe` xong, để
        Worker chỉ bắt đầu chạy khi client chắc chắn đang nhận event (`docs/async-api-doc.md`
        mục 1). Dùng cho `POST /conversations` (mục 1.2) và nhánh "không có turn đang chạy"
        của `send_message`.
        """
        await self._apply_model_choice(conversation_id, model_id)

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

        assistant_message = Message(
            id=new_message_id(),
            conversation_id=conversation_id,
            role="assistant",
            content="",
            status="queued",
            extra={"reasoning": []},
        )
        await self._messages.create(assistant_message)

        await redis_set(
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
                is_steer=False,
                attachments=_turn_attachments(metadata),
            ),
        )
        return user_message, assistant_message

    async def send_message(
        self, conversation_id: str, body: SendMessageInput
    ) -> SendMessageResult:
        """`POST /conversations/{id}/messages` (mục 2.1) — turn mới hoặc Steer tuỳ có
        turn đang chạy hay không (Redis `AGENT_ACTIVE_TURN_KEY`)."""
        active_turn_id = await redis_get(
            AGENT_ACTIVE_TURN_KEY.format(conversation_id=conversation_id)
        )

        metadata = _metadata_from_input(body)

        if active_turn_id is None:
            # Không có turn nào đang chạy -> đây là tin nhắn mở đầu turn mới.
            user_message, assistant_message = await self.start_new_turn(
                conversation_id=conversation_id,
                content=body.content,
                metadata=metadata,
                corr_id=body.client_message_id,
                model_id=body.model_id,
            )
            return SendMessageResult(
                user_message=_to_output(user_message),
                assistant_message=_to_output(assistant_message),
            )

        # Có turn đang chạy -> Steer: worker xử lý NGAY SAU khi turn hiện tại xong (hàng
        # đợi theo `conversation_id`, xem `app/agent/worker.py`) — không còn `pre_step`
        # append giữa chừng như bản Turn/Step/Reasoning cũ, nên `status="done"` ngay,
        # không có trạng thái "pending chờ append" trung gian nữa.
        # Turn ĐANG chạy đã lấy model lúc bắt đầu (`AgentContext.model` set 1 lần khi
        # `worker.py::_drive` bắt đầu turn) nên đổi ở đây không ảnh hưởng turn đó — có
        # hiệu lực từ chính turn Steer này trở đi (worker resolve model MỚI NHẤT từ DB
        # mỗi lần `_drive`, kể cả cho Steer).
        await self._apply_model_choice(conversation_id, body.model_id)
        user_message = Message(
            id=new_message_id(),
            conversation_id=conversation_id,
            role="user",
            content=body.content,
            status="done",
            extra=metadata.model_dump(mode="json", exclude_none=True)
            if metadata is not None
            else None,
        )
        await self._messages.create(user_message)

        # HOÃN publish (giống turn mới), KHÔNG publish thẳng: worker.py xử lý tuần tự
        # theo `conversation_id` (1 lock/hội thoại) — turn ĐANG chạy sẽ tự đóng SSE hiện
        # tại (`STREAM_DONE_SENTINEL`) trước khi Steer này tới lượt xử lý, nên KHÔNG thể
        # giả định SSE cũ vẫn còn mở lúc Steer thực sự chạy. Client cần mở lại
        # `GET .../stream` (đúng cơ chế `flush_pending_turn` đã có cho turn mới) để nhận
        # event của Steer.
        await self._defer_turn(
            conversation_id,
            TurnRequest(
                type="turn",
                conversation_id=conversation_id,
                message_id=active_turn_id,
                corr_id=body.client_message_id,
                content=body.content,
                is_steer=True,
                attachments=_turn_attachments(metadata),
            ),
        )

        assistant_message = await self._messages.get(active_turn_id)
        assistant_output = (
            _to_output(assistant_message)
            if assistant_message is not None
            else MessageOutput(
                id=active_turn_id,
                conversation_id=conversation_id,
                role="assistant",
                content="",
                status="streaming",
                metadata=None,
                created_at=user_message.created_at.isoformat(),
            )
        )
        return SendMessageResult(
            user_message=_to_output(user_message),
            assistant_message=assistant_output,
        )

    async def answer_question(
        self, conversation_id: str, question_id: str, body: MessageAnswerDto
    ) -> MessageOutput:
        """`POST /conversations/{id}/questions/{questionId}/answer` (mục 2.2) — hoãn
        "resume request" vào Redis `agent:pending_turn:*` (giống turn mới), KHÔNG tạo
        `messages` row mới (mục 4). Worker resume khi client mở lại SSE."""
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
                # Resume gửi TEXT thuần cho tool `ask_user` (`app/agent/tools.py`) —
                # không còn 1 DTO chờ/resume riêng như bản Turn/Step/Reasoning cũ,
                # `question_id` chỉ dùng để Core tìm ĐÚNG message đang chờ ở trên, không
                # cần forward tiếp cho Worker (1 hội thoại chỉ có ĐÚNG 1 câu hỏi đang
                # chờ tại 1 thời điểm).
                answer=body.label or body.option_id,
            ),
        )
        return _to_output(message)

    async def _defer_turn(self, conversation_id: str, req: TurnRequest) -> None:
        """Lưu `TurnRequest` chờ flush (handler SSE publish sau khi subscribe)."""
        await redis_set(
            AGENT_PENDING_TURN_KEY.format(conversation_id=conversation_id),
            req.model_dump_json(),
            ex_seconds=settings.AGENT_TURN_KEY_TTL,
        )


async def flush_pending_turn(conversation_id: str) -> None:
    """Đẩy `TurnRequest` đang chờ (nếu có) của `conversation_id` vào `agent_request_queue`.

    Gọi từ handler SSE NGAY SAU khi `pubsub.subscribe()` hoàn tất — lúc này client chắc
    chắn nhận được mọi event Worker phát ra. `GETDEL` đảm bảo dù client mở nhiều SSE
    connection cùng lúc thì chỉ 1 lần publish. Chỉ đụng Redis + RabbitMQ (không cần DB
    session) nên an toàn gọi trong generator của `StreamingResponse`.
    """
    key = AGENT_PENDING_TURN_KEY.format(conversation_id=conversation_id)
    payload = await redis_get_del(key)
    if not payload:
        return
    try:
        await rabbitmq_client.publish(AGENT_REQUEST_QUEUE, payload.encode("utf-8"))
    except Exception:
        # Publish hỏng SAU khi đã GETDEL — trả `payload` lại Redis để lần mở SSE kế tiếp
        # (client tự reconnect) thử lại, tránh mất turn / assistant row kẹt "queued".
        await redis_set(key, payload, ex_seconds=settings.AGENT_TURN_KEY_TTL)
        raise


def _metadata_from_input(body: SendMessageInput) -> MessageMetadataDto | None:
    if body.attachments is None and body.selection is None:
        return None
    return MessageMetadataDto(attachments=body.attachments, selection_ref=body.selection)


def _turn_attachments(metadata: MessageMetadataDto | None) -> list[TurnAttachment] | None:
    """Chỉ forward attachment ẢNH cho Worker — `classify_skin_image`
    (`app/agent/tools/skin_image_classifier.py`) là consumer DUY NHẤT hiện tại của
    `TurnRequest.attachments`, các loại file khác (nếu FE cho phép sau này) không có ý
    nghĩa với Agent nên không cần gửi qua RabbitMQ."""
    if not metadata or not metadata.attachments:
        return None
    images = [a for a in metadata.attachments if a.type.startswith("image/")]
    if not images:
        return None
    return [TurnAttachment(name=a.name, type=a.type, object_key=a.id) for a in images]


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
