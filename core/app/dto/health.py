"""DTO cho /health, /health/ready — ví dụ minh hoạ quy ước validate response bằng Pydantic."""
from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessChecks(BaseModel):
    database: str
    redis: str
    rabbitmq: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: ReadinessChecks
