"""Truy vấn DB cho `ConsultationSession`, `PreConsultationReport`, `ClinicalFact`."""
from datetime import UTC, datetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation_session import ConsultationSession
from app.models.clinical import (
    ClinicalFact,
    ClinicalFactTemplate,
    PreConsultationReport,
)


class ConsultationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_session(self, session: ConsultationSession) -> ConsultationSession:
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_session(self, session_id: str) -> ConsultationSession | None:
        stmt = select(ConsultationSession).where(ConsultationSession.id == session_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self, status: str | None = None, doctor_id: str | None = None
    ) -> list[ConsultationSession]:
        stmt = select(ConsultationSession).order_by(ConsultationSession.requested_at.desc())
        if doctor_id:
            # bác sĩ chỉ thấy ca chờ nhận và ca của chính mình, không thấy ca bác sĩ khác đang phụ trách
            stmt = stmt.where(
                or_(ConsultationSession.status == "pending", ConsultationSession.doctor_id == doctor_id)
            )
        if status and status != "all":
            stmt = stmt.where(ConsultationSession.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_open_session_by_conversation(
        self, conversation_id: str
    ) -> ConsultationSession | None:
        """Mỗi hội thoại tối đa 1 phiên đang mở (status != resolved)."""
        stmt = (
            select(ConsultationSession)
            .where(
                ConsultationSession.conversation_id == conversation_id,
                ConsultationSession.status != "resolved",
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_report(self, session_id: str) -> PreConsultationReport | None:
        stmt = select(PreConsultationReport).where(
            PreConsultationReport.consultation_session_id == session_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_report(
        self, report: PreConsultationReport
    ) -> PreConsultationReport:
        self._db.add(report)
        await self._db.flush()
        return report

    async def get_clinical_facts_by_patient(
        self, patient_profile_id: str
    ) -> list[tuple[ClinicalFact, ClinicalFactTemplate]]:
        stmt = (
            select(ClinicalFact, ClinicalFactTemplate)
            .join(ClinicalFactTemplate, ClinicalFact.template_id == ClinicalFactTemplate.id)
            .where(ClinicalFact.patient_profile_id == patient_profile_id)
            .order_by(ClinicalFact.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return [(r[0], r[1]) for r in result.all()]

    async def get_or_create_template(
        self, fact_type: str, label: str
    ) -> ClinicalFactTemplate:
        stmt = select(ClinicalFactTemplate).where(ClinicalFactTemplate.label == label)
        result = await self._db.execute(stmt)
        tpl = result.scalar_one_or_none()
        if tpl:
            return tpl
        tpl = ClinicalFactTemplate(
            fact_type=fact_type,
            label=label,
        )
        self._db.add(tpl)
        await self._db.flush()
        return tpl

    async def add_clinical_facts(
        self, facts: list[ClinicalFact]
    ) -> list[ClinicalFact]:
        for fact in facts:
            self._db.add(fact)
        await self._db.flush()
        return facts

    async def accept_session(
        self, session: ConsultationSession, doctor_id: str
    ) -> ConsultationSession:
        session.status = "active"
        session.doctor_id = doctor_id
        session.started_at = datetime.now(UTC)
        await self._db.flush()
        return session

    async def resolve_session(
        self, session: ConsultationSession
    ) -> ConsultationSession:
        session.status = "resolved"
        session.resolved_at = datetime.now(UTC)
        await self._db.flush()
        return session
