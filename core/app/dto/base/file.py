from pydantic import BaseModel


class File(BaseModel):
    """Một file lưu trên object storage (MinIO) — dùng chung cho mọi entity có file đính kèm (xem `Document`).
    `storage_key` là khoá đầy đủ trong bucket, không phải đường dẫn tương đối trong thư mục của entity."""

    file_name: str
    storage_key: str
    content_type: str | None = None
    size: int | None = None  # bytes
    created_at: str | None = None
