"""LLM dùng chung: lấy chat model theo id + gọi trả JSON (retry khi JSON hỏng, cache theo hash trong MinIO).

Chỉ mượn model từ agent (`agent.llm.get_model`) — import lười để test không phải nạp
LangChain khi chạy toàn luật hay khi dùng LLM giả. Client ĐỒNG BỘ vì pipeline chạy ở thread nền riêng."""

import hashlib
import json
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from typing import Protocol


def sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def get_chat_model(model_id: str) -> Any:
    """Chat model LangChain theo id (provider:model hoặc id ngắn trong `settings.AGENT_MODEL_CHOICES`); cấu hình provider ở `agent/llm.py`."""
    from agent.llm import get_model

    return get_model(model_id)


class LLMError(RuntimeError):
    pass


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


# Lỗi LLM hay mắc: thiếu dấu nháy đóng của khoá ("confidence: 0.9 -> "confidence": 0.9).
_MISSING_KEY_QUOTE = re.compile(r'"(\w+):\s*(?=[\d"\[{tfn-])')


def _repair(text: str) -> str:
    return _MISSING_KEY_QUOTE.sub(r'"\1": ', text)


def extract_json(text: str) -> Any:
    """Lấy JSON trong câu trả lời (chịu ```json fence, lời dẫn thừa, vài lỗi cú pháp quen thuộc).

    KHÔNG BAO GIỜ trả về một object con khi cả tài liệu hỏng: từng có lỗi thật — JSON sai một chỗ
    trong lô 60 heading, parser "cứu" object con đầu tiên và cả lô bị mất im lặng. Hỏng thì raise
    để nơi gọi retry hoặc chia nhỏ lô."""
    text = _FENCE.sub("", text.strip())
    m = re.search(r"[\[{]", text)
    if m is None:
        raise LLMError(f"không tìm thấy JSON trong phản hồi: {text[:200]!r}")
    dec = json.JSONDecoder()
    body = text[
        m.start() :
    ]  # bỏ lời dẫn trước JSON; chỉ thử từ ký tự { / [ ĐẦU TIÊN
    for candidate in (body, _repair(body)):
        try:
            obj, _ = dec.raw_decode(candidate)
            return obj
        except json.JSONDecodeError:
            continue
    raise LLMError(
        f"JSON không hợp lệ trong phản hồi ({len(text)} ký tự): {text[:120]!r}..."
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p if isinstance(p, str) else str(p.get("text", ""))
            for p in content
            if isinstance(p, (str, dict))
        )
    return str(content)


class BlobCache(Protocol):
    """Kho bytes theo tên cho cache phản hồi (vd `FileStoreService.scoped("_cache/llm/")`)."""

    def get_bytes(self, name: str) -> bytes | None: ...

    def put_bytes(self, name: str, data: bytes, content_type: str | None = None) -> None: ...


class LLMClient:
    def __init__(
        self,
        model: str = "",
        *,
        cache_dir: Path | None = None,
        cache: BlobCache | None = None,
        fn: Callable[[str, str], str] | None = None,
    ):
        """Cache phản hồi theo hash: ở thư mục `cache_dir` (test) hoặc ở kho file `cache` (khoá `<2 ký tự>/<hash>.json`); không truyền gì
        = không cache. `fn(system, user) -> text` thay LLM thật (dùng trong test)."""
        self.model_id = model
        self.cache_dir = cache_dir
        self._cache = cache
        self._fn = fn
        self._model: Any = None
        self._lock = threading.Lock()
        self.stats = {
            "calls": 0,
            "cache_hits": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "failures": 0,
        }

    # ---- model ----
    def _resolved_model(self) -> str:
        from app.config.settings import settings

        m = self.model_id or settings.AGENT_DEFAULT_MODEL_ID
        return settings.AGENT_MODEL_CHOICES.get(m, m)

    def _invoke(self, system: str, user: str) -> str:
        if self._fn is not None:
            return self._fn(system, user)
        from langchain_core.messages import HumanMessage, SystemMessage

        if self._model is None:
            self._model = get_chat_model(self._resolved_model())
        resp = self._model.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        usage = getattr(resp, "usage_metadata", None) or {}
        with self._lock:
            self.stats["input_tokens"] += int(usage.get("input_tokens", 0))
            self.stats["output_tokens"] += int(usage.get("output_tokens", 0))
        return _content_to_text(resp.content)

    # ---- cache ----
    def _cache_key(self, key: str) -> str:
        return f"{key[:2]}/{key}.json"

    def _cache_read(self, key: str) -> str | None:
        if self.cache_dir is not None:
            p = self.cache_dir / key[:2] / f"{key}.json"
            return p.read_text(encoding="utf-8") if p.exists() else None
        if self._cache is None:
            return None
        raw = self._cache.get_bytes(self._cache_key(key))
        return None if raw is None else raw.decode("utf-8")

    def _cache_write(self, key: str, text: str) -> None:
        if self.cache_dir is not None:
            p = self.cache_dir / key[:2] / f"{key}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return
        if self._cache is None:
            return
        self._cache.put_bytes(self._cache_key(key), text.encode("utf-8"), "application/json")

    def complete_json(
        self, system: str, user: str, *, name: str = "", retries: int = 2
    ) -> Any:
        model_key = "fake" if self._fn is not None else self._resolved_model()
        key = sha(model_key, system, user)
        raw: str | None = None
        cached = self._cache_read(key)
        if cached is not None:
            try:
                raw = json.loads(cached)["response"]
                with self._lock:
                    self.stats["cache_hits"] += 1
            except (json.JSONDecodeError, KeyError):
                raw = None

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            if raw is None:
                try:
                    raw = self._invoke(
                        system, user if attempt == 0 else user + _RETRY_NUDGE
                    )
                except Exception as e:  # lỗi mạng/API: thử lại
                    last_err = e
                    with self._lock:
                        self.stats["failures"] += 1
                    continue
                with self._lock:
                    self.stats["calls"] += 1
            try:
                data = extract_json(raw)
            except LLMError as e:
                last_err = e
                raw = None  # đừng cache phản hồi hỏng
                continue
            if cached is None:
                self._cache_write(
                    key,
                    json.dumps(
                        {"model": model_key, "name": name, "response": raw},
                        ensure_ascii=False,
                    ),
                )
            return data
        raise LLMError(
            f"LLM thất bại sau {retries + 1} lần ({name}): {last_err}"
        )


_RETRY_NUDGE = (
    "\n\nCHỈ trả về một JSON hợp lệ, không thêm lời dẫn hay markdown."
)
