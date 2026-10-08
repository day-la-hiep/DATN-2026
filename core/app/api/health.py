"""Health check endpoints — dùng cho liveness/readiness probe và debug thủ công.

Đồng thời làm ví dụ quy ước DTO: response được validate/serialize qua Pydantic
model trong `app/dto/response/health.py` thay vì trả dict tay.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_postgres_client, get_rabbitmq_client, get_redis_client
from app.dto.response.health import LivenessResponse, ReadinessChecks, ReadinessResponse
from app.infra.postgres_client import PostgresClient
from app.infra.rabbitmq_client import RabbitMQClient
from app.infra.redis_client import RedisClient

router = APIRouter(tags=["health"])


@router.get("/health", response_model=LivenessResponse, operation_id="liveness")
async def liveness() -> LivenessResponse:
    """Liveness: app còn sống (không kiểm tra dependency)."""
    return LivenessResponse()


@router.get(
    "/health/ready",
    operation_id="readiness",
    responses={
        200: {"model": ReadinessResponse, "description": "Mọi dependency đều ok"},
        503: {"model": ReadinessResponse, "description": "Ít nhất 1 dependency lỗi"},
    },
)
async def readiness(
    postgres: Annotated[PostgresClient, Depends(get_postgres_client)],
    redis: Annotated[RedisClient, Depends(get_redis_client)],
    rabbitmq: Annotated[RabbitMQClient, Depends(get_rabbitmq_client)],
) -> JSONResponse:
    """Readiness: kiểm tra kết nối tới Postgres, Redis, RabbitMQ.

    Trả JSONResponse thủ công (không dùng response_model) vì cần tự set status
    code 200/503 theo kết quả check — DTO vẫn được dùng để validate nội dung
    trước khi serialize. `responses=` ở decorator chỉ để khai báo schema cho
    OpenAPI (Swagger UI, `docs/openapi.yaml`), không ảnh hưởng hành vi thật.
    """
    database = "ok"
    try:
        await postgres.ping()
    except Exception as exc:  # noqa: BLE001
        database = f"error: {exc}"

    redis_status = "ok"
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error: {exc}"

    rabbitmq_status = "ok" if rabbitmq.is_connected else "error: not connected"

    checks = ReadinessChecks(database=database, redis=redis_status, rabbitmq=rabbitmq_status)
    healthy = all(v == "ok" for v in checks.model_dump().values())
    body = ReadinessResponse(status="ok" if healthy else "degraded", checks=checks)

    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())
