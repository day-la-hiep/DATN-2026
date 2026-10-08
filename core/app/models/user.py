from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    # DB sinh id (`gen_random_uuid()`); 64 ký tự để chứa cả id cố định của dữ liệu mẫu (`user-1`, `doctor-1`...)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(16))  # `Gender`
    # nullable: tài khoản mẫu tạo trước khi có đăng nhập chưa có mật khẩu
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    # default (Python-side, không phải server_default) để có giá trị ngay sau
    # flush() mà không cần round-trip RETURNING.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
