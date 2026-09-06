from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import aggregator để đăng ký toàn bộ ORM model trước create_all.
import app.models  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.agent.response_consumer import start_consuming
from app.api.conversation_api import router as conversation_router
from app.api.health import router as health_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.infra.rabbitmq_client import rabbitmq_client
from app.infra.redis_client import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB: tạo bảng cho dev. Production nên dùng Alembic migration thay vì create_all.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # RabbitMQ: mở 1 connection/channel dùng chung cho toàn app.
    await rabbitmq_client.connect()
    # Consumer `agent_response_queue` — Core là writer duy nhất của bảng `messages` cho
    # kết quả Agent Worker trả về (`docs/async-api-doc.md` mục 6). `consume()` chỉ đăng
    # ký callback rồi return ngay (không block) — an toàn gọi trước `yield`.
    await start_consuming()

    yield

    await rabbitmq_client.close()
    await redis_client.aclose()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(conversation_router, prefix=settings.API_V1_PREFIX)


@app.get("/status", operation_id="status", tags=["health"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.PROJECT_NAME} is running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3050, reload=True, env_file=".env")
