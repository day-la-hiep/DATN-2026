"""DTO cho resource Conversation (`docs/api-doc.md` mục 1)."""
from pydantic import field_validator

from app.core.config import settings
from app.dto.common import CamelModel


def _validate_model_id(model: str) -> str:
    if model not in settings.AGENT_MODEL_CHOICES:
        choices = ", ".join(settings.AGENT_MODEL_CHOICES)
        raise ValueError(f'model="{model}" không hợp lệ — chỉ nhận: {choices}.')
    return model


class ModelOption(CamelModel):
    """1 lựa chọn model cho FE hiển thị dropdown (`GET /models`) — `id` là giá trị gửi
    lên `CreateConversationInput.model`/`UpdateConversationModelInput.model`."""

    id: str


class ConversationOutput(CamelModel):
    id: str
    title: str
    model: str
    created_at: str
    updated_at: str


class CreateConversationInput(CamelModel):
    """Body cho `POST /conversations` — tạo hội thoại kèm tin nhắn đầu tiên
    (`docs/api-doc.md` mục 1.2)."""

    user_id: str
    init_message: str
    title: str | None = None
    # id trong `AGENT_MODEL_CHOICES` (`app/core/config.py`) — bỏ trống dùng
    # `AGENT_DEFAULT_MODEL_ID`.
    model: str | None = None

    _validate_model = field_validator("model")(
        lambda v: _validate_model_id(v) if v is not None else v
    )


class UpdateConversationModelInput(CamelModel):
    """Body cho `PATCH /conversations/{id}/model` — đổi model dùng cho các turn KẾ TIẾP
    của hội thoại (turn đang chạy dở không bị ảnh hưởng)."""

    model: str

    _validate_model = field_validator("model")(_validate_model_id)
