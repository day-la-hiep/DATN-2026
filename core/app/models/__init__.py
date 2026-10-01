"""Aggregator: import toàn bộ model ở đây để `Base.metadata` nhận diện được
cho Alembic autogenerate (xem `migrations/env.py`).
"""
from app.models.book import Book, BookOverride, BookStage  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.conversation import Conversation  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.message import Message  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.user import User  # noqa: F401  # pyright: ignore[reportUnusedImport]
