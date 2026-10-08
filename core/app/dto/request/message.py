"""DTO Input cho resource Message"""
from pydantic import BaseModel

from app.dto.common import AnsweredChoice, FileDto


class SendMessageInput(BaseModel):
    """Body cho `POST /conversations/{id}/messages`"""

    client_message_id: str
    content: str
    model_id: str | None = None
    attached_files: list[FileDto] | None = None  # object nhận từ `POST /uploads`


class MessageAnswerDto(AnsweredChoice):
    """Body cho `POST .../questions/{question_id}/answer`"""

    question_id: str
