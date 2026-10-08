"""Envelope response chung"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envelope chuẩn cho response 1 object/list"""

    data: T
