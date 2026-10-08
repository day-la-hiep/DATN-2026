"""DTO Output cho resource Conversation"""

from pydantic import BaseModel


class ModelOption(BaseModel):
    """1 lựa chọn model cho FE hiển thị dropdown"""

    id: str


class ConversationOutput(BaseModel):
    id: str
    title: str
    model: str
    created_at: str
    updated_at: str
