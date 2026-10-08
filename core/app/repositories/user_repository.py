"""Truy vấn DB cho `User` (`app/models/user.py`) và kiểm tra vai trò người dùng."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import Admin
from app.models.doctor import Doctor
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: str) -> User | None:
        """Tìm user theo ID."""
        return await self._db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        """Tìm user theo username duy nhất."""
        stmt = select(User).where(User.username == username)
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Tạo mới một user và flush để nhận ID do DB sinh."""
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def get_role(self, user_id: str) -> str:
        """Xác định vai trò của user: admin, doctor, hoặc patient."""
        admin_stmt = select(Admin.user_id).where(Admin.user_id == user_id)
        if (await self._db.execute(admin_stmt)).scalar_one_or_none() is not None:
            return "admin"

        doctor_stmt = select(Doctor.user_id).where(Doctor.user_id == user_id)
        if (await self._db.execute(doctor_stmt)).scalar_one_or_none() is not None:
            return "doctor"

        return "patient"
