from datetime import timedelta
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

from app.config.settings import settings

_MISSING = {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}


class MinioClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False) -> None:
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    @classmethod
    def from_settings(cls) -> "MinioClient":
        return cls(settings.MINIO_ENDPOINT, settings.MINIO_ACCESS_KEY, settings.MINIO_SECRET_KEY, settings.MINIO_SECURE)

    def ensure_bucket(self, bucket: str) -> None:
        """Tạo bucket nếu chưa có (idempotent)."""
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(bucket, key, BytesIO(data), length=len(data), content_type=content_type)

    def put_file(self, bucket: str, key: str, path: Path, content_type: str = "application/octet-stream") -> None:
        self.client.fput_object(bucket, key, str(path), content_type=content_type)

    def get_bytes(self, bucket: str, key: str) -> bytes | None:
        """Nội dung đối tượng; `None` khi không tồn tại (lỗi khác như AccessDenied vẫn raise)."""
        try:
            resp = self.client.get_object(bucket, key)
        except S3Error as e:
            if e.code in _MISSING:
                return None
            raise
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def download(self, bucket: str, key: str, dest: Path) -> None:
        self.client.fget_object(bucket, key, str(dest))

    def size(self, bucket: str, key: str) -> int | None:
        try:
            return int(self.client.stat_object(bucket, key).size or 0)
        except S3Error as e:
            if e.code in _MISSING:
                return None
            raise

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        """Mọi key (đệ quy) bắt đầu bằng `prefix`."""
        return [o.object_name for o in self.client.list_objects(bucket, prefix=prefix, recursive=True) if o.object_name]

    def list_dirs(self, bucket: str, prefix: str) -> list[str]:
        """Tên các "thư mục" con trực tiếp của `prefix` (không kèm prefix và dấu `/`)."""
        return [o.object_name[len(prefix):].strip("/") for o in self.client.list_objects(bucket, prefix=prefix, recursive=False)
                if o.is_dir and o.object_name]

    def delete(self, bucket: str, key: str) -> None:
        self.client.remove_object(bucket, key)

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        errors = list(self.client.remove_objects(bucket, [DeleteObject(k) for k in self.list_keys(bucket, prefix)]))
        if errors:
            raise RuntimeError(f"Không xoá được {len(errors)} đối tượng trong MinIO: {errors[0]}")

    def presigned_get_url(self, bucket: str, key: str, expires: timedelta) -> str:
        return self.client.presigned_get_object(bucket, key, expires=expires)
