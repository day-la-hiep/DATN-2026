"""Aggregator: import toàn bộ model ở đây để `Base.metadata` nhận diện được
cho Alembic autogenerate (xem `migrations/env.py`).
"""
from app.models.file import File  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.document import Document, DocumentOverride, DocumentStage  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.message_file import MessageFile  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.video_call import VideoCall  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.conversation import Conversation  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.message import Message  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.user import User  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.doctor import Doctor  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.admin import Admin  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.patient_profile import PatientProfile  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.models.consultation_session import ConsultationSession  # noqa: F401  # pyright: ignore[reportUnusedImport]
