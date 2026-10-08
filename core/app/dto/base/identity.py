"""Bounded context Định danh: tài khoản (`User`, `Doctor`, `Admin`) và hồ sơ bệnh nhân (`PatientProfile`)."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.common.constant import Gender

if TYPE_CHECKING:
    # import chéo context chỉ để type-check; vòng tham chiếu được rebuild một lần trong `app/dto/base/__init__.py`
    from app.dto.base.clinical import ClinicalFact
    from app.dto.base.medical_record import MedicalRecord


class User(BaseModel):
    id: str
    username: str
    full_name: str
    dob: date
    gender: Gender
    password_hash: str | None = None  # None: tài khoản chưa đặt mật khẩu (dữ liệu mẫu), chưa đăng nhập được
    patient_profiles: list[PatientProfile]


class Doctor(User):
    description: str


class Admin(User):
    pass


class PatientProfile(BaseModel):
    id: str
    full_name: str
    dob: date
    gender: Gender
    medical_records: list[MedicalRecord] = []
    clinical_facts: list[ClinicalFact] = []  # dữ kiện lâm sàng của người bệnh, gom từ nhiều hội thoại hoặc bác sĩ nhập
