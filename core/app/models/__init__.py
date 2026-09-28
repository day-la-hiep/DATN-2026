"""Aggregator: import toàn bộ model ở đây để `Base.metadata` nhận diện được
trước khi gọi `create_all` (xem `main.py`).
"""
from app.models.conversation import Conversation  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.message import Message  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.user import User  # noqa: F401  # pyright: ignore[reportUnusedImport]
