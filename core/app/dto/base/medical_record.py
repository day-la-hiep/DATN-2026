"""Bounded context Bệnh án: bệnh án do bác sĩ ghi và ảnh bệnh kèm theo."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.dto.base.identity import Doctor
    from app.dto.base.shared import File


class MedicalRecord(BaseModel):
    """Bệnh án của một hồ sơ bệnh nhân (`PatientProfile.medical_records`), do bác sĩ ghi sau một lượt khám."""

    id: str
    diagnosis: str
    notes: str = ""
    doctor: Doctor | None = None
    images: list[PatientImage] = []
    # ca bệnh tham khảo: bác sĩ xác nhận dùng làm dữ liệu cho KB / chatbot tra ca tương tự (ẩn định danh khi đưa vào KB)
    is_reference_case: bool = False
    created_at: datetime | None = None


class PatientImage(BaseModel):
    """Ảnh bệnh được bác sĩ gắn vào bệnh án. `file` có thể dùng lại file bệnh nhân đã gửi trong chat (cùng dòng `files`)."""

    id: str
    file: File
    body_site: str = ""  # vị trí trên cơ thể
    description: str = ""
    confirmed_label: str | None = None  # nhãn bác sĩ xác nhận — dữ liệu huấn luyện CNN
    captured_at: datetime | None = None
