"""PatientProfile — hồ sơ bệnh nhân (`app/dto/base/user.py::PatientProfile`). Tách bảng vì một tài khoản quản lý được nhiều hồ
sơ (bản thân, người thân) — `User.patient_profiles` là danh sách."""
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(16))  # `Gender`
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
