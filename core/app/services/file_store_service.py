"""Kho file generic trên MinIO"""

import logging
import asyncio
import json
import os
import tempfile
import uuid
from collections.abc import Iterable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, TypedDict

from fastapi import UploadFile
from minio.error import S3Error

from app.infra.minio_client import MinioClient

logger = logging.getLogger(__name__)

# Ảnh đính kèm: chỉ nhận ảnh — phạm vi hiện tại là input cho skin CNN classifier, không phải upload file đa dụng.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_PRESIGNED_URL_TTL = timedelta(days=7)


class StoredUpload(TypedDict):
    id: str
    name: str
    size: int
    type: str
    url: str


def content_type_for(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".jsonl"):
        return "application/x-ndjson"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".yaml"):
        return "application/yaml"
    if name.endswith((".log", ".txt")):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


class FileStoreService:
    def __init__(self, minio: MinioClient, bucket: str, prefix: str = "") -> None:
        self._minio, self.bucket, self.prefix = minio, bucket, prefix

    def scoped(self, prefix: str) -> "FileStoreService":
        """View con dưới `prefix` (tương đối với view hiện tại)."""
        return FileStoreService(self._minio, self.bucket, self.key(prefix))

    def ensure_bucket(self) -> None:
        self._minio.ensure_bucket(self.bucket)

    def key(self, name: str) -> str:
        """Object key đầy đủ của `name`; chặn tên trỏ ra ngoài tiền tố."""
        if name.startswith("/") or ".." in name.split("/"):
            raise ValueError("tên file ra ngoài thư mục cho phép")
        return self.prefix + name

    # ---- bytes / file ----
    def size(self, name: str) -> int | None:
        return self._minio.size(self.bucket, self.key(name))

    def exists(self, name: str) -> bool:
        return self.size(name) is not None

    def get_bytes(self, name: str) -> bytes | None:
        return self._minio.get_bytes(self.bucket, self.key(name))

    def put_bytes(self, name: str, data: bytes, content_type: str | None = None) -> None:
        self._minio.put_bytes(self.bucket, self.key(name), data, content_type or content_type_for(name))

    def put_file(self, name: str, path: Path, content_type: str | None = None) -> None:
        self._minio.put_file(self.bucket, self.key(name), path, content_type or content_type_for(name))

    def delete(self, name: str) -> None:
        self._minio.delete(self.bucket, self.key(name))

    def delete_prefix(self, prefix: str = "") -> None:
        self._minio.delete_prefix(self.bucket, self.key(prefix))

    def list_names(self, prefix: str = "") -> list[str]:
        """Tên (tương đối với view) của mọi file có tiền tố `prefix`."""
        return [k[len(self.prefix):] for k in self._minio.list_keys(self.bucket, self.key(prefix))]

    def list_dirs(self, prefix: str = "") -> list[str]:
        """Tên các "thư mục" con trực tiếp của `prefix`."""
        return self._minio.list_dirs(self.bucket, self.key(prefix))

    def local_copy(self, name: str, dest: Path) -> Path:
        """Bản sao trên đĩa của `name` cho công cụ cần file thật"""
        size = self.size(name)
        if size is None:
            raise FileNotFoundError(name)
        if not dest.exists() or dest.stat().st_size != size:
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".part")
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                self._minio.download(self.bucket, self.key(name), tmp)
                tmp.replace(dest)
            finally:
                tmp.unlink(missing_ok=True)
        return dest

    # ---- text / JSON / JSONL ----
    def get_text(self, name: str) -> str | None:
        raw = self.get_bytes(name)
        return None if raw is None else raw.decode("utf-8")

    def put_text(self, name: str, text: str) -> None:
        self.put_bytes(name, text.encode("utf-8"))

    def read_json(self, name: str, default: Any = None) -> Any:
        raw = self.get_bytes(name)
        return default if raw is None else json.loads(raw.decode("utf-8"))

    def write_json(self, name: str, data: Any) -> None:
        self.put_text(name, json.dumps(data, ensure_ascii=False, indent=1))

    def iter_jsonl(self, name: str) -> Iterator[dict[str, Any]]:
        raw = self.get_bytes(name)
        if raw is None:
            return
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                yield json.loads(line)

    def read_jsonl(self, name: str) -> list[dict[str, Any]]:
        return list(self.iter_jsonl(name))

    def write_jsonl(self, name: str, rows: Iterable[dict[str, Any]]) -> None:
        self.put_text(name, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    # ---- ảnh đính kèm tin nhắn (async) ----
    async def ensure_bucket_async(self) -> None:
        """Tạo bucket nếu chưa có — gọi 1 lần lúc Core khởi động (`main.py::lifespan`, idempotent)."""
        await asyncio.to_thread(self.ensure_bucket)

    async def save_upload(self, file: UploadFile) -> StoredUpload:
        """`id` trả về = object key — `get_object_bytes(id)` dùng lại đúng giá trị này để đọc lại, không cần bảng ánh xạ riêng."""
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError(f"Định dạng không hỗ trợ: {file.content_type}")

        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(f"File vượt quá {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")

        suffix = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
        name = f"{uuid.uuid4().hex}.{suffix}"
        content_type = file.content_type or "application/octet-stream"

        def _put() -> str:
            self.put_bytes(name, data, content_type)
            return self.presigned_url(name)

        url = await asyncio.to_thread(_put)
        return StoredUpload(id=name, name=file.filename or name, size=len(data), type=content_type, url=url)

    def presigned_url(self, name: str) -> str:
        """Link tạm để FE xem trước file (không lưu: tạo lại mỗi lần trả tin nhắn vì link hết hạn)."""
        return self._minio.presigned_get_url(self.bucket, self.key(name), _PRESIGNED_URL_TTL)

    async def get_object_bytes(self, name: str) -> bytes | None:
        """Đọc lại ảnh theo object key"""
        try:
            return await asyncio.to_thread(self.get_bytes, name)
        except ValueError:
            return None
        except S3Error as exc:
            # Lỗi khác NoSuchKey (AccessDenied, InvalidAccessKeyId...) là lỗi cấu hình MinIO — log để phân biệt với "key sai/đã xoá".
            logger.warning("get_object failed: code=%s key=%r bucket=%r", exc.code, name, self.bucket)
            return None
