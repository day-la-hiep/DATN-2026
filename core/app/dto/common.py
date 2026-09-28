"""DTO dùng chung cho nhiều resource (envelope response, phân trang, camelCase...)."""
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base DTO: field Python `snake_case`, wire JSON `camelCase` (`api-doc.md` mục 0).

    `populate_by_name=True` để vẫn nhận input bằng tên Python gốc (test, code nội bộ)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiResponse(BaseModel, Generic[T]):
    """Envelope chuẩn cho response 1 object/list: `{"data": ...}`.

    Dùng làm response_model:
        @router.get("/items/{id}", response_model=ApiResponse[ItemOutput])
        def get_item(...) -> ApiResponse[ItemOutput]:
            return ApiResponse(data=ItemOutput(...))
    """

    data: T


class PageParams(BaseModel):
    """Query params phân trang dùng chung."""

    page: int = 1
    page_size: int = 20


class PageResponse(BaseModel, Generic[T]):
    """Envelope response cho danh sách có phân trang."""

    data: list[T]
    page: int
    page_size: int
    total: int
