"""Bản rút gọn của entity `consultation` / `identity` để hiển thị cho FE"""
from datetime import datetime

from pydantic import BaseModel

from app.common.constant import ConsultationStatus


class DoctorDto(BaseModel):
    """`app/dto/base/identity.py::Doctor` rút gọn — chỉ phần cần hiển thị trong luồng chat."""

    id: str
    full_name: str
    description: str = ""


class ConsultationSessionDto(BaseModel):
    """`app/dto/base/consultation.py::ConsultationSession` với `doctor` rút gọn, không kèm `report` / `video_calls`."""

    doctor: DoctorDto | None = None
    status: ConsultationStatus = ConsultationStatus.PENDING
    reason: str
    requested_at: datetime | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
