from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageFile(Base):
    __tablename__ = "message_files"

    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(64), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
