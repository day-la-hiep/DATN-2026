from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import aggregator: đăng ký toàn bộ ORM model (relationship giữa các model cần đủ mapper).
import app.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from agent.handler.response_consumer import start_consuming
from app.api.auth_api import router as auth_router
from app.api.conversation_api import router as conversation_router
from app.api.deps import close_clients, get_file_store_service, get_rabbitmq_client
from app.api.health import router as health_router
from app.api.document_api import router as document_router
from app.api.upload_api import router as upload_router
from app.api.doctor_api import router as doctor_router
from app.config.auth import require_app_token
from app.config.settings import log_startup_infra, settings
from app.exception.exception_handler import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_infra()

    # Schema DB do Alembic quản lý (`uv run alembic upgrade head`, xem `migrations/`) — không tạo bảng ở đây.

    # Dữ liệu mẫu (user-1 mà FE hard-code, bác sĩ, admin) do `scripts/init_db.py` tạo — Core khởi động không ghi dữ liệu.

    # RabbitMQ: mở 1 connection/channel dùng chung cho toàn app.
    await get_rabbitmq_client().connect()
    # Consumer `agent_response_queue` — Core là writer duy nhất của bảng `messages` cho
    # kết quả Agent Worker trả về (`docs/async-api-doc.md` mục 6). `consume()` chỉ đăng
    # ký callback rồi return ngay (không block) — an toàn gọi trước `yield`.
    await start_consuming()
    # MinIO: bucket ảnh đính kèm (app/services/file_store_service.py) — idempotent.
    await get_file_store_service().ensure_bucket_async()

    yield

    await close_clients()  # RabbitMQ, Redis, Postgres, Qdrant... mọi client đã tạo


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "REST API cho chat + Agent reasoning (xem `core/docs/api-doc.md`). Luồng SSE "
        "(`GET /conversations/{conversationId}/stream`) không nằm trong OpenAPI này — "
        "xem `core/docs/asyncapi.yaml` / `async-api-doc.md`."
    ),
    servers=[{"url": "http://localhost:3050", "description": "Local dev"}],
    lifespan=lifespan,
)

register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(
    conversation_router,
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(require_app_token)],
)
app.include_router(
    document_router,
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(require_app_token)],
)
app.include_router(
    upload_router,
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(require_app_token)],
)
app.include_router(
    doctor_router,
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(require_app_token)],
)


@app.get("/status", operation_id="status", tags=["health"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} is running"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app", host="0.0.0.0", port=3050, reload=True, env_file=".env"
    )
