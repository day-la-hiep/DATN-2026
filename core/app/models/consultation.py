"""Consultation & Pre-consultation Report models (thi_t_k_database.md mục 2.2.4)."""
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ConsultationSession(Base):
    __tablename__ = "consultation_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    doctor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending, active, resolved
    reason: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Quan hệ 1-1 với báo cáo tiền tư vấn AI
    report: Mapped["PreConsultationReport | None"] = relationship(
        "PreConsultationReport",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # Quan hệ 1-n với các dữ kiện lâm sàng đã trích xuất
    clinical_facts: Mapped[list["ClinicalFact"]] = relationship(
        "ClinicalFact",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PreConsultationReport(Base):
    __tablename__ = "pre_consultation_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consultation_session_id: Mapped[str] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    session: Mapped["ConsultationSession"] = relationship(
        "ConsultationSession", back_populates="report"
    )


class ClinicalFact(Base):
    __tablename__ = "clinical_facts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consultation_session_id: Mapped[str] = mapped_column(
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"), index=True
    )
    template_label: Mapped[str] = mapped_column(String(255))
    fact_type: Mapped[str] = mapped_column(String(32))  # symptom, lesion, history, medication, allergy, image_finding, other
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    session: Mapped["ConsultationSession"] = relationship(
        "ConsultationSession", back_populates="clinical_facts"
    )
