"""User — tối thiểu cho `userId` truyền tay từ client (chưa có auth thật, xem
`docs/api-doc.md` mục 0)."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    # 64 (không phải 36 = độ dài UUID trần) vì `new_user_id()` (`app/core/ids.py`) sinh
    # id có tiền tố resource (`user-<uuid4>` = 41 ký tự).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    # Dự phòng auth thật (session/JWT) — chưa dùng.
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    # default (Python-side, không phải server_default) để có giá trị ngay sau
    # flush() mà không cần round-trip RETURNING.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
