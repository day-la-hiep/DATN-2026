"""Admin — đánh dấu tài khoản quản trị (`app/dto/base/identity.py::Admin`). Chưa có field riêng; PK = FK tới `users.id` (1-1)."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Admin(Base):
    __tablename__ = "admins"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
