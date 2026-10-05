"""Truy vấn DB cho `PatientProfile` (`app/models/patient_profile.py`)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import PatientProfile


class PatientProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def first_for_user(self, user_id: str) -> PatientProfile | None:
        """Hồ sơ tạo sớm nhất của tài khoản — dùng làm hồ sơ mặc định khi API chưa cho chọn hồ sơ."""
        stmt = (
            select(PatientProfile)
            .where(PatientProfile.user_id == user_id)
            .order_by(PatientProfile.created_at.asc())
            .limit(1)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()
