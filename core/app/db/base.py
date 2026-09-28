"""Base class dùng chung cho toàn bộ SQLAlchemy ORM model."""
from sqlalchemy.orm import DeclarativeBase

# Naming convention cho constraint (index/fk/uq/ck/pk) — giúp Alembic autogenerate
# đặt tên nhất quán, tránh migration bị lệch tên constraint giữa các lần chạy.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class cho toàn bộ model. Import model cụ thể trong `app/models/`."""

    pass


Base.metadata.naming_convention = NAMING_CONVENTION
