"""DTO cho resource Consultation và Pre-consultation Report."""
from pydantic import BaseModel


class PatientProfileDto(BaseModel):
    id: str
    full_name: str
    dob: str
    gender: str


class ClinicalFactOutput(BaseModel):
    id: str
    template_label: str
    fact_type: str
    detail: str
    status: str
    created_at: str


class PreConsultationReportOutput(BaseModel):
    id: str
    summary: str
    created_at: str


class ConsultationSessionOutput(BaseModel):
    id: str
    conversation_id: str
    conversation_title: str
    patient: PatientProfileDto
    doctor_id: str | None = None
    status: str
    reason: str
    requested_at: str
    started_at: str | None = None
    resolved_at: str | None = None
    report: PreConsultationReportOutput | None = None
    clinical_facts: list[ClinicalFactOutput] = []


class RequestConsultationInput(BaseModel):
    reason: str = "Bệnh nhân yêu cầu bác sĩ tư vấn"


class DoctorReplyInput(BaseModel):
    content: str
