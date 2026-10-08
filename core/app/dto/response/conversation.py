"""DTO Output cho resource Conversation (`docs/api-doc.md` mục 1). Base `Conversation` chưa có id/tiêu đề/model —
các field này lấy từ bảng `conversations`."""

from pydantic import BaseModel


class ModelOption(BaseModel):
    """1 lựa chọn model cho FE hiển thị dropdown (`GET /models`) — `id` là giá trị gửi
    lên `CreateConversationInput.model`/`UpdateConversationModelInput.model`."""

    id: str


class ConversationOutput(BaseModel):
    id: str
    title: str
    model: str
    created_at: str
    updated_at: str
