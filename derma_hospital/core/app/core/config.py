"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# `pydantic-settings`' `env_file` chỉ nạp giá trị vào field ĐÃ KHAI BÁO trong `Settings`
# — biến provider-specific không khai báo ở đây (vd `GOOGLE_API_KEY` cho
# `langchain-google-genai`, đọc trực tiếp qua `os.environ`) sẽ KHÔNG được nạp bằng cách
# đó. `core/main.py` (`uvicorn.run(..., env_file=".env")`) nạp hộ cho tiến trình Core,
# nhưng `app/agent/worker.py` (tiến trình riêng, `python -m app.agent.worker`) không có
# cơ chế tương đương — gọi `load_dotenv()` ở đây để cả 2 tiến trình đều nhất quán, không
# phụ thuộc uvicorn.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "Derma AI Backend"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ----- PostgreSQL (SQLAlchemy async engine, driver asyncpg) -----
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/derma_hospital_db"
    )

    # ----- Redis (Pub/Sub) -----
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ----- RabbitMQ -----
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # ----- Qdrant (long-term memory — vector DB, xem app/agent/memory.py) -----
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "agent_memories"

    # ----- CORS -----
    CORS_ORIGINS: list[str] = ["*"]

    # ----- Agent (LangChain / LangGraph) -----
    # Cú pháp "provider:model" cho langchain.chat_models.init_chat_model.
    # Provider "google_genai" cần package "langchain[google-genai]" (đã khai trong
    # pyproject.toml) + biến môi trường GOOGLE_API_KEY trong .env.
    AGENT_MODEL: str = "google_genai:gemini-3.5-flash-lite"
    AGENT_TEMPERATURE: float = 0.3
    AGENT_MAX_REASONING_STEPS: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
