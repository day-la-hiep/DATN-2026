"""Đổi khoá camelCase -> snake_case cho dữ liệu đã lưu trước khi API chuyển sang snake_case (summary trong
`document_stages`, `choice` trong `messages.metadata`). Đọc-rồi-đổi để không phải migrate dữ liệu cũ."""
import re
from typing import Any

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def snake_keys(value: Any, *, deep: bool = False) -> Any:
    """Khoá đã là snake_case giữ nguyên. `deep=True` đổi cả dict/list lồng bên trong."""
    if isinstance(value, dict):
        return {_CAMEL.sub("_", k).lower() if isinstance(k, str) else k: (snake_keys(v, deep=True) if deep else v)
                for k, v in value.items()}
    if deep and isinstance(value, list):
        return [snake_keys(v, deep=True) for v in value]
    return value
