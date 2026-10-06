"""DTO Input cho resource Message (`docs/api-doc.md` mục 2). Field cùng nghĩa với `app/dto/base/conversation.py::Message`/
`MessageMetadata` dùng cùng tên: `content`, `attached_files`."""
from pydantic import BaseModel

from app.dto.common import AnsweredChoice, FileDto


class SendMessageInput(BaseModel):
    """Body cho `POST /conversations/{id}/messages` (`api-doc.md` mục 2.1).

    KHÔNG có field `answer` — trả lời câu hỏi agent đi qua endpoint riêng
    (`docs/async-api-doc.md` mục 4), không phải tin nhắn mới.
    """

    client_message_id: str
    content: str
    model_id: str | None = None
    attached_files: list[FileDto] | None = None  # object nhận từ `POST /uploads`


class MessageAnswerDto(AnsweredChoice):
    """Body cho `POST .../questions/{question_id}/answer` (`api-doc.md` mục 2.2). Kế thừa `AnsweredChoice` (common) — thêm
    `question_id` để biết trả lời câu hỏi nào."""

    question_id: str
