"""MinIO giả trong bộ nhớ cho test (cùng chữ ký với `MinioClient` ở phần `FileStoreService` dùng)."""
from pathlib import Path


class MemoryMinio:
    """Thay `MinioClient`: mọi bucket dùng chung một dict `objects` (test chỉ có một bucket sách)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_bucket(self, bucket: str) -> None:
        pass

    def get_bytes(self, bucket: str, key: str) -> bytes | None:
        return self.objects.get(key)

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = bytes(data)

    def put_file(self, bucket: str, key: str, path: Path, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = Path(path).read_bytes()

    def download(self, bucket: str, key: str, dest: Path) -> None:
        dest.write_bytes(self.objects[key])

    def size(self, bucket: str, key: str) -> int | None:
        return len(self.objects[key]) if key in self.objects else None

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))

    def list_dirs(self, bucket: str, prefix: str) -> list[str]:
        return sorted({k[len(prefix):].split("/", 1)[0] for k in self.objects if k.startswith(prefix) and "/" in k[len(prefix):]})

    def delete(self, bucket: str, key: str) -> None:
        self.objects.pop(key, None)

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        for k in self.list_keys(bucket, prefix):
            del self.objects[k]
