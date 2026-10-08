"""Truy vấn DB cho `ConsultationSession`, `PreConsultationReport`, `ClinicalFact`."""
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.consultation import (
    ConsultationSession,
    PreConsultationReport,
    ClinicalFact,
)


class ConsultationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_session(self, session: ConsultationSession) -> ConsultationSession:
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_session(self, session_id: str) -> ConsultationSession | None:
        stmt = (
            select(ConsultationSession)
            .where(ConsultationSession.id == session_id)
            .options(
                selectinload(ConsultationSession.report),
                selectinload(ConsultationSession.clinical_facts),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self, status: str | None = None
    ) -> list[ConsultationSession]:
        stmt = (
            select(ConsultationSession)
            .options(
                selectinload(ConsultationSession.report),
                selectinload(ConsultationSession.clinical_facts),
            )
            .order_by(ConsultationSession.requested_at.desc())
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
            .options(
                selectinload(ConsultationSession.report),
                selectinload(ConsultationSession.clinical_facts),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_report(
        self, report: PreConsultationReport
    ) -> PreConsultationReport:
        self._db.add(report)
        await self._db.flush()
        return report

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
