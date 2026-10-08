"""DTO cho resource Consultation và Pre-consultation Report."""
from app.dto.common import CamelModel


class PatientProfileDto(CamelModel):
    id: str
    full_name: str
    dob: str
    gender: str


class ClinicalFactOutput(CamelModel):
    id: str
    template_label: str
    fact_type: str
    detail: str
    status: str
    created_at: str


class PreConsultationReportOutput(CamelModel):
    id: str
    summary: str
    created_at: str


class ConsultationSessionOutput(CamelModel):
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


class RequestConsultationInput(CamelModel):
    reason: str = "Bệnh nhân yêu cầu bác sĩ tư vấn"


class DoctorReplyInput(CamelModel):
    content: str
