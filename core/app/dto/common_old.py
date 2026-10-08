"""DTO dùng chung cho nhiều resource"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envelope chuẩn cho response 1 object/list"""

    data: T


class FileDto(BaseModel):
    """File trên wire"""

    file_name: str
    storage_key: str
    content_type: str | None = None
    size: int | None = None
    created_at: str | None = None
    url: str | None = None
