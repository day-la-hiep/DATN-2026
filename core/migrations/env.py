"""Alembic: URL lấy từ `settings.DATABASE_URL` (đổi driver async -> psycopg đồng bộ), schema từ `app.models` (`Base.metadata`).

Tạo migration:  `uv run alembic revision --autogenerate -m "mô tả"`  (kiểm tra lại file sinh ra trước khi commit)
Áp migration:   `uv run alembic upgrade head`"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  # pyright: ignore[reportUnusedImport] — đăng ký mọi model vào Base.metadata
from app.config.settings import settings
from app.models.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", "+psycopg"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
