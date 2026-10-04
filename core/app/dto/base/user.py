from __future__ import annotations

from pydantic import BaseModel
from datetime import date

from app.common.constant import Gender


class User(BaseModel):
    id: str
    username: str
    full_name: str
    dob: date
    gender: Gender
    patient_profiles: list[PatienProfile]


class PatienProfile(BaseModel):
    id: str
    full_name: str
    dob: date
    gender: Gender


class Doctor(User):
    description: str


class Admin(User):
    pass
