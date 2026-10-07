"""Log tập trung cho cả Core và Agent Worker (2 process riêng, mỗi process gọi `setup_logging`
đúng 1 lần lúc khởi động). Mọi module chỉ cần `logging.getLogger(__name__)` — không tự cấu
hình handler. Format: `HH:MM:SS.mmm LEVEL service logger  message`, có màu khi chạy trong
terminal (tắt bằng `NO_COLOR=1`, ép bật bằng `FORCE_COLOR=1` khi pipe qua `less -R`/docker)."""

import logging
import os
import sys
import time
import traceback
import uuid
from contextvars import ContextVar

from app.config.settings import settings

# Request id gắn vào log của mọi dòng phát sinh trong cùng 1 request HTTP (rỗng ở worker).
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_LEVEL_COLORS = {
    "DEBUG": "\033[36m",  # cyan
    "INFO": "\033[32m",  # green
    "WARNING": "\033[33m",  # vàng
    "ERROR": "\033[31m",  # đỏ
    "CRITICAL": "\033[1;97;41m",  # chữ trắng nền đỏ
}
_TRACE_COLORS = {"NODE": "\033[35m", "LLM": "\033[36m", "TOOL": "\033[33m"}
_SERVICE_COLORS = {"core": "\033[1;34m", "worker": "\033[1;35m", "cli": "\033[1;36m"}

# Thư viện ồn ở mức INFO (mỗi request/poll in 1 dòng) — hạ xuống WARNING để log ứng dụng dễ đọc.
_NOISY_LOGGERS = (
    "httpx", "httpx2", "httpcore", "numexpr", "urllib3", "aio_pika", "aiormq", "pika", "asyncio",
    "sentence_transformers", "filelock", "langsmith", "openai", "qdrant_client",
    "sqlalchemy.engine", "uvicorn.access",
)


def _status_color(status: int) -> str:
    if status >= 500:
        return "\033[1;31m"
    if status >= 400:
        return "\033[33m"
    if status >= 300:
        return "\033[36m"
    return "\033[32m"


class ColorFormatter(logging.Formatter):
    def __init__(self, service: str, use_color: bool) -> None:
        super().__init__()
        self.service = service
        self.use_color = use_color

    def _paint(self, text: str, color: str) -> str:
        return f"{color}{text}{_RESET}" if self.use_color else text

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created)) + f".{int(record.msecs):03d}"
        level = record.levelname
        # Rút gọn "app.services.document_service" -> giữ nguyên nhưng căn lề để các cột thẳng hàng.
        name = record.name if len(record.name) <= 28 else "…" + record.name[-27:]
        rid = request_id_var.get()
        parts = [
            self._paint(ts, _DIM),
            self._paint(f"{level:<8}", _LEVEL_COLORS.get(level, "")),
            self._paint(f"{self.service:<6}", _SERVICE_COLORS.get(self.service, "")),
            self._paint(f"{name:<28}", "\033[34m"),
        ]
        if rid:
            parts.append(self._paint(rid, _DIM))
        message = record.getMessage()
        if record.name == "agent.trace" and self.use_color:
            # NODE / LLM / TOOL mỗi loại một màu để quét mắt theo vòng lặp graph.
            kind, _, rest = message.partition(" ")
            message = f"{_TRACE_COLORS.get(kind, '')}{_BOLD}{kind}{_RESET} {rest}"
        elif record.levelno >= logging.ERROR:
            message = self._paint(message, _LEVEL_COLORS[level] if level == "ERROR" else _BOLD)
        parts.append(message)
        line = " ".join(parts)
        if record.exc_info and record.exc_info[0] is not None:
            tb = "".join(traceback.format_exception(*record.exc_info)).rstrip()
            line += "\n" + self._paint(tb, "\033[31m")
        return line


def _color_enabled(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


def setup_logging(service: str) -> None:
    """`service`: "core", "worker" hoặc "cli" (TUI `agent/test/cli.py`) — hiện ở cột thứ 3 để phân biệt khi xem chung 1 màn hình."""
    stream = sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColorFormatter(service, _color_enabled(stream)))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())

    # uvicorn tự gắn handler + propagate=False cho logger của nó; gỡ ra để đi qua handler chung
    # (nếu không log khởi động/lỗi của uvicorn sẽ có format riêng, lệch với phần còn lại).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


class RequestLogMiddleware:
    """Thay access log của uvicorn: thêm request id + thời gian xử lý. Viết dạng ASGI thuần
    (không dùng `BaseHTTPMiddleware`) để không làm vỡ stream SSE của `/conversations/{id}/stream`."""

    def __init__(self, app) -> None:
        self.app = app
        self.logger = logging.getLogger("http")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = request_id_var.set(uuid.uuid4().hex[:8])
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            ms = (time.perf_counter() - start) * 1000
            color = _status_color(status)
            # Màu của status nhúng trực tiếp vào message; formatter tắt màu thì ta cũng bỏ mã ANSI.
            use_color = _color_enabled(sys.stdout)
            code = f"{color}{status}{_RESET}" if use_color else str(status)
            level = logging.ERROR if status >= 500 else logging.INFO
            self.logger.log(
                level, "%s %s -> %s %.0fms", scope["method"], scope["path"], code, ms
            )
            request_id_var.reset(token)
