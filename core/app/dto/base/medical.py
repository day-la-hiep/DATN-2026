from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MedicalRecord(BaseModel):
    patient_id: str
    diagnosis: str
    notes: str = ""
    created_at: datetime | None = None


class ClinicalInfo(BaseModel):
    description: str


class SupportRequest(BaseModel):
    reason: str
    status: Literal["open", "resolved"] = "open"
    created_at: datetime | None = None
