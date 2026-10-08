"""Conversation — 1 cuộc hội thoại của 1 user (`docs/db-diagram.md` mục 1)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.config.settings import settings
from app.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    # DB sinh id (`gen_random_uuid()`); hội thoại cũ giữ id dạng `conv-<uuid>` nên cột vẫn là chuỗi 64
    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))
    # `Conversation.patient` (base). Tài khoản sở hữu hội thoại = `patient_profiles.user_id` — không lưu lặp ở đây.
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"))
    title: Mapped[str] = mapped_column(String(255), default="")
    # id ngắn trong `AGENT_MODEL_CHOICES` (`app/config/settings.py`), KHÔNG phải chuỗi
    # "provider:model" thật — worker tự map sang chuỗi thật lúc chạy turn
    # (`agent/context/builder.py::_conversation_for`) để đổi danh sách model không cần
    # migration cột này. Chọn 1 lần lúc tạo hội thoại, đổi được sau qua `PATCH
    # /conversations/{id}/model` (`app/api/conversation_api.py`).
    model: Mapped[str] = mapped_column(
        String(32), default=lambda: settings.AGENT_DEFAULT_MODEL_ID
    )
    # default/onupdate Python-side (SQLAlchemy tự tính trước khi INSERT/UPDATE) —
    # không dùng server_default để có giá trị ngay sau flush(), không cần RETURNING.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
