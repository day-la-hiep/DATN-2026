"""MedicalRecord / PatientImage"""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    # bác sĩ bị xoá thì bệnh án vẫn giữ
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.user_id", ondelete="SET NULL"), default=None)
    diagnosis: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_reference_case: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PatientImage(Base):
    __tablename__ = "patient_images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    medical_record_id: Mapped[str] = mapped_column(ForeignKey("medical_records.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(String(64), ForeignKey("files.id", ondelete="CASCADE"))
    body_site: Mapped[str] = mapped_column(String(128), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # nhãn bác sĩ xác nhận, nên khớp tên lớp của CNN để dùng làm dữ liệu huấn luyện
    confirmed_label: Mapped[str | None] = mapped_column(String(128), default=None)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
