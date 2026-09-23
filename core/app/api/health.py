"""Health check endpoints — dùng cho liveness/readiness probe và debug thủ công.

Đồng thời làm ví dụ quy ước DTO: response được validate/serialize qua Pydantic
model trong `app/dto/health.py` thay vì trả dict tay.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.dto.health import LivenessResponse, ReadinessChecks, ReadinessResponse
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import redis_client

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
async def readiness() -> JSONResponse:
    """Readiness: kiểm tra kết nối tới Postgres, Redis, RabbitMQ.

    Trả JSONResponse thủ công (không dùng response_model) vì cần tự set status
    code 200/503 theo kết quả check — DTO vẫn được dùng để validate nội dung
    trước khi serialize. `responses=` ở decorator chỉ để khai báo schema cho
    OpenAPI (Swagger UI, `docs/openapi.yaml`), không ảnh hưởng hành vi thật.
    """
    database = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database = f"error: {exc}"

    redis_status = "ok"
    try:
        await redis_client.ping()
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error: {exc}"

    rabbitmq_status = "ok" if rabbitmq_client.is_connected else "error: not connected"

    checks = ReadinessChecks(database=database, redis=redis_status, rabbitmq=rabbitmq_status)
    healthy = all(v == "ok" for v in checks.model_dump().values())
    body = ReadinessResponse(status="ok" if healthy else "degraded", checks=checks)

    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())
