"""PostgreSQL dùng chung: class `PostgresClient` = SQLAlchemy async engine + session factory + `ping`, kèm engine ĐỒNG BỘ (psycopg) cho code
chạy trong thread nền (pipeline sách). Vòng đời session theo request
(commit/rollback) nằm ở `app/api/deps.py::get_db`; instance do deps tạo và `dispose()` lúc tắt."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings


class PostgresClient:
    def __init__(self, url: str, *, pool_pre_ping: bool = True, echo: bool = False, expire_on_commit: bool = False,
                 autoflush: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=pool_pre_ping, echo=echo)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine, expire_on_commit=expire_on_commit, autoflush=autoflush)
        # cùng DB, driver đồng bộ: `postgresql+asyncpg://` -> `postgresql+psycopg://`
        self.sync_engine = create_engine(url.replace("+asyncpg", "+psycopg"), pool_pre_ping=pool_pre_ping, echo=echo)
        self.sync_session_factory: sessionmaker[Session] = sessionmaker(bind=self.sync_engine, expire_on_commit=False)

    @classmethod
    def from_settings(cls) -> "PostgresClient":
        return cls(settings.DATABASE_URL, pool_pre_ping=settings.DATABASE_POOL_PRE_PING, echo=settings.DEBUG,
                   expire_on_commit=settings.DATABASE_EXPIRE_ON_COMMIT, autoflush=settings.DATABASE_AUTOFLUSH)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Một AsyncSession ngoài request (agent worker, consumer): không tự commit — caller tự quyết."""
        async with self.session_factory() as s:
            yield s

    async def ping(self) -> None:
        """Kiểm tra kết nối (raise nếu lỗi) — dùng cho readiness probe."""
        async with self.session_factory() as s:
            await s.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()
        self.sync_engine.dispose()
