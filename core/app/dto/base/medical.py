from datetime import datetime

from pydantic import BaseModel


class MedicalRecord(BaseModel):
    patient_id: str
    diagnosis: str
    notes: str = ""
    created_at: datetime | None = None


class ClinicalInfo(BaseModel):
    description: str
