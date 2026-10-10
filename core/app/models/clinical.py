"""ClinicalFact / PreConsultationReport"""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClinicalFactTemplate(Base):
    __tablename__ = "clinical_fact_templates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    fact_type: Mapped[str] = mapped_column(String(32))  # `ClinicalFactType`
    label: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    ontology_id: Mapped[str | None] = mapped_column(String(128), default=None)


class ClinicalFact(Base):
    __tablename__ = "clinical_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    # fact thuộc về người bệnh, không thuộc một cuộc chat; hội thoại sinh ra fact truy ngược qua `ClinicalProvenance`
    patient_profile_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id", ondelete="CASCADE"), index=True)
    # RESTRICT: không xoá được mẫu đang có fact dùng, tránh mất ngữ nghĩa của fact đã ghi
    template_id: Mapped[str] = mapped_column(ForeignKey("clinical_fact_templates.id", ondelete="RESTRICT"), index=True)
    detail: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")  # "active" | "superseded"
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("clinical_facts.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ClinicalProvenance(Base):
    """`ClinicalFact.provenances` — nguồn gốc của fact: `message_id` là tin nhắn gốc làm bằng chứng (`ClinicalProvenance.message`)."""

    __tablename__ = "clinical_provenances"

    fact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinical_facts.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)


class PreConsultationReport(Base):
    __tablename__ = "pre_consultation_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))  # DB sinh
    # 1 báo cáo / phiên tư vấn
    consultation_session_id: Mapped[str] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
