"""File — một file trên MinIO (`app/dto/base/file.py::File`). Nơi dùng trỏ FK tới đây thay vì lặp tên/kích thước:
`documents.source_file_id`/`ingested_file_id`, `message_files` (ảnh đính kèm tin nhắn).

`storage_key` là khoá đầy đủ trong bucket; bucket suy ra từ nơi dùng (tài liệu -> `MINIO_DOCUMENTS_BUCKET`, đính kèm tin nhắn
-> `MINIO_BUCKET`) vì base `File` không có field bucket."""
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, server_default=text("gen_random_uuid()"))
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str | None] = mapped_column(String(128), default=None)
    size: Mapped[int | None] = mapped_column(BigInteger, default=None)  # bytes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
