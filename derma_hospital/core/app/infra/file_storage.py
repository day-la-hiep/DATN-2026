"""Lưu file đính kèm tin nhắn (ảnh da liễu cho `app/agent/tools/skin_image_classifier.py`)
vào MinIO (S3-compatible object storage) — `app/api/upload_api.py` ghi, Agent Worker đọc
lại qua network client bằng object key, KHÔNG cần chung filesystem/host với Core (khác
Qdrant/Neo4j hiện tại vẫn giả định localhost — MinIO tách hẳn state ra khỏi 2 tiến trình).

`minio` SDK là client THUẦN ĐỒNG BỘ (không có async) — mọi lệnh gọi network đều bọc qua
`asyncio.to_thread` để không block event loop của Core/Worker (cùng phong cách "client
module-level + free-function" như `redis_client.py`/`qdrant_client.py`).
"""
import asyncio
import uuid
from datetime import timedelta
from io import BytesIO
from typing import TypedDict

from fastapi import UploadFile
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)

# Chỉ nhận ảnh — phạm vi hiện tại là input cho skin CNN classifier, không phải upload
# file đa dụng.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_PRESIGNED_URL_TTL = timedelta(days=7)


class StoredUpload(TypedDict):
    id: str
    name: str
    size: int
    type: str
    url: str


async def ensure_bucket() -> None:
    """Tạo bucket nếu chưa có — gọi 1 lần lúc Core khởi động (`main.py::lifespan`,
    idempotent)."""
    await asyncio.to_thread(_ensure_bucket_sync)


def _ensure_bucket_sync() -> None:
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


async def save_upload(file: UploadFile) -> StoredUpload:
    """`id` trả về = object key trên MinIO — `get_object_bytes(id)` dùng lại đúng giá
    trị này để đọc lại, không cần bảng ánh xạ riêng."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"Định dạng không hỗ trợ: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File vượt quá {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")

    suffix = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    object_name = f"{uuid.uuid4().hex}.{suffix}"
    content_type = file.content_type or "application/octet-stream"

    def _put() -> str:
        client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return client.presigned_get_object(
            settings.MINIO_BUCKET, object_name, expires=_PRESIGNED_URL_TTL
        )

    url = await asyncio.to_thread(_put)

    return StoredUpload(
        id=object_name,
        name=file.filename or object_name,
        size=len(data),
        type=content_type,
        url=url,
    )


async def get_object_bytes(object_name: str) -> bytes | None:
    """Đọc lại nội dung ảnh theo object key — dùng bởi
    `app/agent/tools/skin_image_classifier.py` lúc chạy inference. `object_name` đi qua
    `SendMessageInput` (client-controlled JSON, không phải lúc nào cũng đúng giá trị
    `save_upload` từng trả về) -> trả `None` khi không tồn tại thay vì raise, tool tự
    báo lỗi cho agent thay vì crash turn."""
    try:
        response = await asyncio.to_thread(
            client.get_object, settings.MINIO_BUCKET, object_name
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except S3Error:
        return None
