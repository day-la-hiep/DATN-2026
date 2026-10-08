"""Envelope response chung. Mọi request/response dùng snake_case trên wire, đúng tên field Python — không dùng alias
camelCase."""
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
