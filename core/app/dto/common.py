"""DTO dùng chung cho nhiều resource (envelope response, file). Mọi request/response dùng snake_case trên wire, đúng
tên field Python — không dùng alias camelCase."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envelope chuẩn cho response 1 object/list: `{"data": ...}`.

    Dùng làm response_model:
        @router.get("/items/{id}", response_model=ApiResponse[ItemOutput])
        def get_item(...) -> ApiResponse[ItemOutput]:
            return ApiResponse(data=ItemOutput(...))
    """

    data: T


class FileDto(BaseModel):
    """File trên wire — field khớp `app/dto/base/shared.py::File`. `url` là field riêng của API: link presigned để FE xem
    trước, sinh lúc upload, không lưu trong base."""

    file_name: str
    storage_key: str
    content_type: str | None = None
    size: int | None = None
    created_at: str | None = None
    url: str | None = None
