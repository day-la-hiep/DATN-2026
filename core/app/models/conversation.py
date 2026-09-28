"""Conversation — 1 cuộc hội thoại của 1 user (`docs/db-diagram.md` mục 1)."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    # 64 (không phải 36 = độ dài UUID trần) vì `new_conversation_id()` (`app/core/ids.py`)
    # sinh id có tiền tố resource (`conv-<uuid4>` = 41 ký tự).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), default="")
    # id ngắn trong `AGENT_MODEL_CHOICES` (`app/core/config.py`), KHÔNG phải chuỗi
    # "provider:model" thật — worker tự map sang chuỗi thật lúc chạy turn
    # (`app/agent/worker.py::_conversation_for`) để đổi danh sách model không cần
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
