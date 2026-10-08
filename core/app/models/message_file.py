"""MessageFile — tệp đính kèm của tin nhắn (`MessageMetadata.attached_files` của base). Bảng nối thay vì chép `File` vào
`messages.metadata`: mỗi file một nguồn sự thật trong `files`, và biết được file nào không còn tin nhắn nào dùng."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageFile(Base):
    __tablename__ = "message_files"

    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(64), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
