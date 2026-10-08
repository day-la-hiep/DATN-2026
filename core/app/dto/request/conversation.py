"""DTO Input cho resource Conversation (`docs/api-doc.md` mục 1)."""

from pydantic import BaseModel, field_validator

from app.config.settings import settings


def _validate_model_id(model: str) -> str:
    if model not in settings.AGENT_MODEL_CHOICES:
        choices = ", ".join(settings.AGENT_MODEL_CHOICES)
        raise ValueError(f'model="{model}" không hợp lệ — chỉ nhận: {choices}.')
    return model


class CreateConversationInput(BaseModel):
    """Body cho `POST /conversations` — tạo hội thoại kèm tin nhắn đầu tiên (`docs/api-doc.md` mục 1.2).
    `content` cùng nghĩa `Message.content` (base) của tin nhắn đầu tiên."""

    user_id: str
    content: str
    title: str | None = None
    # id trong `AGENT_MODEL_CHOICES` (`app/config/settings.py`) — bỏ trống dùng
    # `AGENT_DEFAULT_MODEL_ID`.
    model: str | None = None

    _validate_model = field_validator("model")(
        lambda v: _validate_model_id(v) if v is not None else v
    )


class UpdateConversationModelInput(BaseModel):
    """Body cho `PATCH /conversations/{id}/model` — đổi model dùng cho các turn KẾ TIẾP
    của hội thoại (turn đang chạy dở không bị ảnh hưởng)."""

    model: str

    _validate_model = field_validator("model")(_validate_model_id)
