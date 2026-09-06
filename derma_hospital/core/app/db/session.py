"""SQLAlchemy async engine + session factory + FastAPI dependency."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield 1 AsyncSession request-scoped.

    Tự `commit()` khi route xử lý xong không lỗi (Unit of Work — 1 request = 1
    transaction), tự `rollback()` khi route raise exception. Repository chỉ
    `flush()` (không tự `commit()`) — xem `docs/quy-uoc.md` mục 4.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
