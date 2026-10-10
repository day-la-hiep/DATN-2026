"""Lớp nhập liệu tương tác của TUI: prompt có gợi ý (gõ `/` hiện menu lệnh) và hộp chọn bằng phím mũi tên, dùng `prompt_toolkit`.
Không phải terminal tương tác (pipe, CI) thì rơi về `input()` thường để vẫn script được. Có thể được gọi từ bên trong event loop đang chạy
(vd `ask_user` giữa lượt chat) — `prompt_toolkit` không tự chạy được trong loop đó nên giao diện được chạy ở thread riêng."""
import asyncio
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.shortcuts import choice

T = TypeVar("T")
_history = InMemoryHistory()  # dùng chung cho mọi prompt để ↑ gọi lại câu đã gõ


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _call(fn: Callable[[], T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn).result()


def ask(prompt: str, completer: Completer | None = None) -> str:
    """Ctrl+C -> KeyboardInterrupt, Ctrl+D -> EOFError (giống `input()`)."""
    if not interactive():
        return input(prompt).strip()
    session: PromptSession[str] = PromptSession(history=_history)
    return _call(lambda: session.prompt(prompt, completer=completer, complete_while_typing=True)).strip()


def pick(message: str, options: Sequence[tuple[Any, str]], default: Any = None) -> Any:
    """Hộp chọn ↑/↓ + Enter; trả `value` của lựa chọn. Không tương tác: in danh sách đánh số và đọc số gõ vào (Enter trống = lựa chọn đầu)."""
    if not interactive():
        print(message)
        for i, (_, label) in enumerate(options, 1):
            print(f"  {i}. {label}")
        raw = input("> ").strip()
        by_value = next((v for v, _ in options if str(v) == raw), None)  # cho phép gõ thẳng giá trị (vd "q")
        if by_value is not None:
            return by_value
        return options[int(raw) - 1][0] if raw.isdigit() and 1 <= int(raw) <= len(options) else options[0][0]
    return _call(lambda: choice(message, options=list(options), default=default))
