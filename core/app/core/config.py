"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""

from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = 3 cấp trên file này (core/app/core/config.py -> core/app -> core ->
# derma_hospital) — dùng làm mặc định cho path trỏ ra ngoài core/ (checkpoint model ở
# ../model/, cùng kiểu monorepo-relative-path như data/PrimeKG, data/dermo).
_REPO_ROOT = Path(__file__).resolve().parents[3]

# `pydantic-settings`' `env_file` chỉ nạp giá trị vào field ĐÃ KHAI BÁO trong `Settings`
# — biến provider-specific không khai báo ở đây (vd `GOOGLE_API_KEY` cho
# `langchain-google-genai`, đọc trực tiếp qua `os.environ`) sẽ KHÔNG được nạp bằng cách
# đó. `core/main.py` (`uvicorn.run(..., env_file=".env")`) nạp hộ cho tiến trình Core,
# nhưng `app/agent/worker.py` (tiến trình riêng, `python -m app.agent.worker`) không có
# cơ chế tương đương — gọi `load_dotenv()` ở đây để cả 2 tiến trình đều nhất quán, không
# phụ thuộc uvicorn.
# `_DOTENV_PATH` rỗng = không tìm thấy `.env` -> mọi field fallback về default khai báo
# trong `Settings`, vốn được giữ khớp 1-1 với `docker-compose.yml` (xem ghi chú ở đầu
# file đó) để dev không cần tạo `.env` mới chạy được ngay.
_DOTENV_PATH = find_dotenv(usecwd=True)
load_dotenv(_DOTENV_PATH or None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "Derma AI Backend"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ----- PostgreSQL (SQLAlchemy async engine, driver asyncpg) -----
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/derma_hospital_db"

    # ----- Redis (Pub/Sub) -----
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ----- RabbitMQ -----
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # ----- Qdrant (vector DB) -----
    QDRANT_URL: str = "http://localhost:6333"
    # Khớp `QDRANT__SERVICE__API_KEY` của service qdrant trong docker-compose.yml. Rỗng = không
    # gửi api-key (Qdrant không bật auth).
    QDRANT_API_KEY: str = ""
    # Long-term memory: hạ tầng cũ (app/kien-truc-memory.md), hiện KHÔNG được dùng nữa —
    # app/agent/memory.py đã chuyển sang langgraph.store.InMemoryStore. Giữ setting này
    # để không phá vỡ .env hiện có, chưa xoá client (app/infra/qdrant_client.py).
    QDRANT_COLLECTION: str = "agent_memories"
    # Knowledge base guideline (BYT 75/2015, WHO, MedlinePlus) — 435 chunk ingest từ
    # data-ingest/01_normalize/output/diseases/ qua data-ingest/01_normalize/scripts/load_knowledge_base.py,
    # dùng bởi app/agent/tools/knowledge_base_search.py.
    QDRANT_KB_COLLECTION: str = "derma_kb_chunks"
    # Phenotype PrimeKG (tên embed) — `describe_morphology` chuẩn hoá mô tả tự do sang nút
    # phenotype, ingest qua data-ingest/01_normalize/scripts/load_phenotypes.py.
    QDRANT_PHENOTYPE_COLLECTION: str = "derma_phenotypes"

    # ----- Neo4j (knowledge graph da liễu — PrimeKG, xem
    # app/agent/knowledge_graph.py + data/PrimeKG/load_to_neo4j.py) -----
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "derma12345"

    # ----- Web search nguồn uy tín (agent/tools/web_search.py) -----
    # Rỗng = tool trả thông báo "chưa cấu hình", không crash. Tavily lọc domain ngay ở provider
    # (`include_domains`); code vẫn lọc lại phía server.
    TAVILY_API_KEY: str = ""
    TRUSTED_WEB_DOMAINS: list[str] = [
        "aad.org",
        "dermnetnz.org",
        "medlineplus.gov",
        "who.int",
        "nih.gov",
        "cdc.gov",
        "nhs.uk",
        "mayoclinic.org",
        "moh.gov.vn",
        "kcb.vn",
    ]

    # ----- CORS -----
    CORS_ORIGINS: list[str] = ["*"]

    # ----- Agent (LangChain / LangGraph) -----
    # Cú pháp "provider:model" cho langchain.chat_models.init_chat_model.
    # - "google_genai:..." cần package "langchain[google-genai]" + GOOGLE_API_KEY.
    # - "openai:..." dùng cho OpenRouter (API tương thích OpenAI, xem
    #   `app/agent/llm.py::get_model` — set thêm base_url=OPENROUTER_BASE_URL,
    #   api_key=OPENROUTER_API_KEY) — cần package "langchain-openai" (đã khai trong
    #   pyproject.toml). Model hiện dùng: Gemma 4 26B A4B (MoE, 4B active/26B total)
    #   bản TRẢ PHÍ qua OpenRouter (`google/gemma-4-26b-a4b-it`, KHÔNG có hậu tố
    #   `:free`) — tính phí theo token, cần credit trong tài khoản OpenRouter.
    #   ĐÃ TEST: bản `:free` cùng model (và `qwen/qwen3.8-27b:free`) bị OpenRouter/
    #   Google AI Studio giới hạn CỨNG ngay khi request có tool-calling (bind_tools) —
    #   dù chat thường (không tool) vẫn gọi được bình thường. Agent này LUÔN cần
    #   tool-calling để hoạt động nên phải dùng bản trả phí. (`nvidia/nemotron-3-
    #   super-120b-a12b:free` cũng đã verify hoạt động ổn định nếu muốn phương án free.)
    AGENT_MODEL: str = "openai:google/gemma-4-26b-a4b-it"
    AGENT_TEMPERATURE: float = 0.3
    # id ngắn hiển thị FE (dropdown chọn model/conversation, `app/dto/conversation.py`) ->
    # chuỗi "provider:model" thật cho `init_chat_model` (`app/agent/llm.py`). Đổi id
    # (thêm/bớt lựa chọn) KHÔNG cần migration DB — `Conversation.model` chỉ lưu id, map
    # sang chuỗi thật lúc runtime nên id "chết" (model cũ bị gỡ) tự fallback về
    # `AGENT_MODEL` ở `get_model()` (`app/agent/llm.py`) thay vì crash.
    AGENT_MODEL_CHOICES: dict[str, str] = {
        "deepseek-v4-pro": "deepseek:deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek:deepseek-flash",
        "gemma4-26b": "openai:google/gemma-4-26b-a4b-it",
    }
    # id mặc định cho conversation mới không truyền `model` — khớp `AGENT_MODEL` ở trên.
    AGENT_DEFAULT_MODEL_ID: str = "gemma4-26b"
    # (Từng có AGENT_MAX_REASONING_STEPS ở đây — khai báo nhưng chưa bao giờ được nối
    # vào `agent_graph.astream()` làm `recursion_limit`, đã xoá vì gây hiểu lầm là có
    # giới hạn. Vòng lặp tool-calling hiện chỉ bị chặn bởi default `recursion_limit=25`
    # supersteps của LangGraph — vượt ngưỡng đó raise `GraphRecursionError`, đã được
    # `worker.py::_drive` bắt graceful (coi turn là "done" kèm thông báo lỗi) thay vì
    # treo turn.)

    # Chỉ áp dụng khi AGENT_MODEL dùng provider "google_genai" (Gemini "thinking" —
    # xem `app/agent/llm.py`); OpenRouter/model khác không hỗ trợ tham số này.
    AGENT_THINKING_LEVEL: str = "medium"

    # ----- OpenRouter (dùng khi AGENT_MODEL provider = "openai", xem trên) -----
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: str = ""

    # ----- DeepSeek API trực tiếp (dùng khi AGENT_MODEL provider = "deepseek", vd
    # "deepseek:deepseek-v4-flash" — xem app/agent/llm.py) -----
    # Lấy API key tại https://platform.deepseek.com/api_keys. KHÔNG dùng chung
    # OPENROUTER_API_KEY — 2 endpoint khác nhau (api.deepseek.com vs openrouter.ai),
    # key không tương thích chéo.
    DEEPSEEK_API_KEY: str = ""

    # ----- LangSmith (trace mọi lệnh gọi LLM/tool trong `agent_graph`, xem
    # https://smith.langchain.com) -----
    # LangChain tự đọc TRỰC TIẾP từ `os.environ` theo đúng tên biến chuẩn
    # (`LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`/`LANGSMITH_ENDPOINT`),
    # đã có sẵn trong `os.environ` qua `load_dotenv()` ở trên — KHÔNG cần code nào khác
    # để bật tracing, chỉ cần set các biến này trong `.env`. Khai báo lại 2 field không
    # nhạy cảm (TRACING/PROJECT, KHÔNG khai báo API_KEY) ở đây CHỈ để
    # `log_startup_infra()` biết tracing đang bật hay tắt — không phải cơ chế đọc chính,
    # đổi giá trị ở đây không tự bật/tắt tracing nếu `LANGSMITH_TRACING` trong `.env` ghi
    # khác đi (pydantic-settings và `os.environ` đọc cùng biến, luôn khớp nhau khi set
    # qua `.env`).
    LANGSMITH_TRACING: bool = False
    LANGSMITH_PROJECT: str = "derma-hospital"

    # ----- Shared-token auth (bảo vệ demo/test share cho người ngoài, KHÔNG phải hệ
    # thống user auth thật — không user/password/JWT, chỉ 1 token tĩnh dùng chung) -----
    # Rỗng = tắt hoàn toàn (mặc định dev, không phá luồng hiện có). Set giá trị trong
    # .env để bật — mọi request tới API (trừ /health) phải kèm header
    # `Authorization: Bearer <token>` (xem app/core/auth.py).
    APP_ACCESS_TOKEN: str = ""

    # TTL (giây) cho các Redis key phục vụ 1 turn nhưng phụ thuộc client mở SSE:
    # `agent:pending_turn:*` (turn chờ flush) và `agent:active_turn:*`. Nếu client gọi
    # `POST .../messages` rồi không bao giờ mở `GET .../stream`, key tự hết hạn thay vì
    # treo vĩnh viễn (assistant row `status="queued"` còn lại là việc của job reconcile —
    # xem docs/async-api-doc.md mục 7).
    AGENT_TURN_KEY_TTL: int = 60

    # ----- MinIO (object storage — ảnh đính kèm tin nhắn, app/infra/file_storage.py) ---
    # S3-compatible: Core (FastAPI) ghi qua `POST /uploads`, Agent Worker đọc lại bằng
    # object key qua network client (KHÔNG cần chung filesystem/host với Core).
    # Máy dev đã có sẵn 1 instance MinIO chạy ngoài docker-compose.yml của repo này
    # (cổng 9000/9001, CORS đã cấu hình cho localhost:3000/3050) — default khớp
    # credential của instance đó thay vì tạo container riêng gây đụng cổng.
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123"
    MINIO_BUCKET: str = "derma-attachments"
    MINIO_SECURE: bool = False

    # ----- Skin CNN classifier (app/agent/tools/skin_image_classifier.py) -----
    # Checkpoint gốc nằm ở model/ (sibling repo root, xem model/test_cnn.py) — không copy
    # vào core/ để tránh trùng lặp file nặng (44MB), tham chiếu bằng path tương đối.
    SKIN_CNN_CHECKPOINT_PATH: str = str(
        _REPO_ROOT
        / "model"
        / "model_output"
        / "AdaptiveCNN_SkinDisease_v5_best.pth"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def _mask(value: str) -> str:
    """Che phần user:password trong connection string trước khi log ra console."""
    if "://" not in value or "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    _, host_part = rest.split("@", 1)
    return f"{scheme}://***@{host_part}"


def log_startup_infra() -> None:
    """Log các endpoint infra (Postgres/Redis/RabbitMQ/Qdrant/Neo4j/MinIO) mà process
    này SẼ dùng, kèm nguồn giá trị (`.env` nếu tìm thấy file, ngược lại fallback default
    trong `Settings` — vốn khớp `docker-compose.yml`). Gọi 1 lần lúc khởi động ở cả
    `core/main.py` (Core) và `app/agent/worker.py` (Agent Worker) — 2 process riêng biệt,
    mỗi process cần tự xác nhận đang trỏ đúng infra nào (dev local vs. .env override)."""
    source = (
        f".env ({_DOTENV_PATH})"
        if _DOTENV_PATH
        else "docker-compose.yml default (không tìm thấy .env)"
    )
    lines = [
        f"[Infra] cấu hình từ: {source}",
        f"[Infra] PostgreSQL -> {_mask(settings.DATABASE_URL)}",
        f"[Infra] Redis      -> {settings.REDIS_HOST}:{settings.REDIS_PORT}/db{settings.REDIS_DB}",
        f"[Infra] RabbitMQ   -> {_mask(settings.RABBITMQ_URL)}",
        f"[Infra] Qdrant     -> {settings.QDRANT_URL} (collections: {settings.QDRANT_COLLECTION}, {settings.QDRANT_KB_COLLECTION})",
        f"[Infra] Neo4j      -> {settings.NEO4J_URL} (user={settings.NEO4J_USER})",
        f"[Infra] MinIO      -> {settings.MINIO_ENDPOINT} (bucket={settings.MINIO_BUCKET}, secure={settings.MINIO_SECURE})",
        f"[Infra] LangSmith  -> "
        + (
            f"BẬT (project={settings.LANGSMITH_PROJECT})"
            if settings.LANGSMITH_TRACING
            else "TẮT (set LANGSMITH_TRACING=true + LANGSMITH_API_KEY trong .env để bật)"
        ),
    ]
    # `print` thay vì `logging` — uvicorn/asyncio worker không có handler nào cấu hình
    # sẵn cho root logger nên `logger.info` sẽ im lặng, trong khi `print` luôn ra
    # console (đồng nhất với các log "[Agent Worker] ..." hiện có trong `worker.py`).
    for line in lines:
        print(line)
