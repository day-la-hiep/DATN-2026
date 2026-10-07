"""TUI thử nhanh các chức năng của agent / tra cứu, không cần giao diện web:

    cd core && uv run python -m agent.test.cli              # menu chọn chức năng
    cd core && uv run python -m agent.test.cli reasoning    # vào thẳng một chức năng (key trong features.py)

Menu: gõ số hoặc key để vào chức năng, `q` thoát. Trong chức năng: gõ số để chạy preset, gõ chữ để chạy câu của bạn. Lệnh bắt đầu bằng `/`:
`/set <tên> <giá trị>` đổi cài đặt, `/s` xem cài đặt, `/l` liệt kê preset, `/h` trợ giúp, `/b` về menu, `/q` thoát. Ctrl+C: đang chạy thì dừng lượt
đó, đang ở prompt chức năng thì về menu, đang ở menu thì thoát. Dùng chung một event loop nên client Qdrant / Neo4j và model local được giữ giữa
các lần chạy (lần đầu chậm vì tải model). Muốn thêm chức năng: xem `agent/test/features.py`."""
import asyncio
from collections.abc import Iterable
import sys
import time
import uuid
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `core/`

try:
    import readline  # noqa: F401  # chỉ để `input()` có lịch sử + phím mũi tên; không có trên một số nền tảng
except ImportError:
    pass

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from prompt_toolkit.completion import CompleteEvent, Completer, Completion  # noqa: E402
from prompt_toolkit.document import Document  # noqa: E402

from app.config.log import request_id_var, setup_logging  # noqa: E402
from agent.test import ui  # noqa: E402
from agent.test.features import FEATURES, Feature, Preset, Setting  # noqa: E402

console = Console(highlight=False)
_TRUE, _FALSE = {"on", "true", "1", "yes", "y"}, {"off", "false", "0", "no", "n"}


class Quit(Exception):
    """Thoát toàn bộ CLI (khác với `/b`, chỉ về menu)."""


def _ask(prompt: str, completer: Completer | None = None) -> str:
    try:
        return ui.ask(prompt, completer)
    except EOFError:
        raise Quit from None


class SlashCompleter(Completer):
    """Gõ `/` hiện menu lệnh (kèm mô tả); `/set ` gợi ý tên cài đặt rồi giá trị; `/preset ` gợi ý các preset."""

    def __init__(self, feature: Feature, cfg: dict[str, Any]) -> None:
        self.feature, self.cfg = feature, cfg

    def _commands(self) -> list[tuple[str, str]]:
        f = self.feature
        cmds = [("set", "đổi cài đặt")] if f.settings else []
        cmds += [("preset", "chọn preset để chạy")] if f.presets else []
        cmds += [(name, desc) for name, (desc, _) in f.commands.items()]
        cmds += [("s", "xem cài đặt"), ("l", "liệt kê preset"), ("h", "trợ giúp"), ("b", "về menu"), ("q", "thoát")]
        return cmds

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        head, sep, rest = text[1:].partition(" ")
        if not sep:  # đang gõ tên lệnh
            for name, desc in self._commands():
                if name.startswith(head):
                    yield Completion(name, start_position=-len(head), display=f"/{name}", display_meta=desc)
            return
        if head == "preset":
            for i, p in enumerate(self.feature.presets, 1):
                if str(i).startswith(rest):
                    yield Completion(str(i), start_position=-len(rest), display=str(i), display_meta=p.label[:70])
        elif head == "set":
            name, sep2, value = rest.partition(" ")
            if not sep2:  # đang gõ tên cài đặt
                for s in self.feature.settings:
                    if s.name.startswith(name):
                        yield Completion(s.name, start_position=-len(name), display=s.name, display_meta=f"{s.help} [hiện: {_fmt(self.cfg[s.name])}]")
                return
            setting = next((s for s in self.feature.settings if s.name == name), None)
            if setting is None:
                return
            for v in _value_choices(setting, self.cfg):
                if v.startswith(value):
                    yield Completion(v, start_position=-len(value), display=v, display_meta="giá trị hiện tại" if v == _fmt(self.cfg[name]) else "")


def _value_choices(setting: Setting, cfg: dict[str, Any]) -> list[str]:
    if isinstance(setting.default, bool):
        return ["on", "off"]
    if setting.choices:
        return list(setting.choices)
    current = _fmt(cfg[setting.name])
    return [] if current == "(trống)" else [current]  # int/str tự do: chỉ gợi ý giá trị hiện tại


def _parse(setting: Setting, raw: str) -> Any:
    kind = type(setting.default)
    if kind is bool:
        if raw.lower() in _TRUE:
            return True
        if raw.lower() in _FALSE:
            return False
        raise ValueError("chỉ nhận on/off")
    if kind is int:
        return int(raw)
    if setting.choices and raw not in setting.choices:
        raise ValueError("chọn một trong: " + ", ".join(setting.choices))
    return raw


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value) if value != "" else "(trống)"


def _menu_options() -> list[tuple[str, str]]:
    return [*((f.key, f"{f.title} — {f.help[:70]}") for f in FEATURES), ("q", "Thoát")]


def _presets(feature: Feature) -> Table:
    table = Table(title="Preset", title_justify="left", header_style="bold cyan")
    table.add_column("#", justify="right")
    table.add_column("nội dung")
    for i, p in enumerate(feature.presets, 1):
        table.add_row(str(i), p.label)
    return table


def _settings_table(feature: Feature, cfg: dict[str, Any]) -> Table:
    table = Table(title="Cài đặt (đổi bằng /set <tên> <giá trị>)", title_justify="left", header_style="bold cyan")
    table.add_column("tên", style="green")
    table.add_column("giá trị", style="yellow")
    table.add_column("ý nghĩa", style="dim")
    for s in feature.settings:
        table.add_row(s.name, _fmt(cfg[s.name]), s.help)
    return table


def _help(feature: Feature | None = None) -> None:
    extra = "".join(f"\n[green]/{name}[/]  {desc}" for name, (desc, _) in (feature.commands if feature else {}).items())
    console.print(Panel(
        "số → chạy preset · chữ → chạy câu của bạn\n"
        "[green]/set <tên> <giá trị>[/]  đổi cài đặt     [green]/s[/]  xem cài đặt     [green]/l[/]  liệt kê preset\n"
        "[green]/b[/]  về menu     [green]/q[/]  thoát     [green]Ctrl+C[/]  dừng lượt đang chạy / về menu / thoát" + extra,
        title="Trợ giúp", title_align="left"))


async def _execute(feature: Feature, text: str, cfg: dict[str, Any], preset: Preset | None, loop: asyncio.AbstractEventLoop) -> None:
    request_id_var.set(uuid.uuid4().hex[:8])  # gắn mã lượt vào mọi dòng log (NODE/LLM/TOOL) của lần chạy này
    console.rule(f"[bold]{feature.title}[/]  [dim]{text[:80]}[/]")
    start = time.perf_counter()
    task = loop.create_task(feature.run(text, cfg, preset))
    try:
        await task
    except asyncio.CancelledError:
        console.print("[yellow](đã dừng)[/]")
    except Exception as exc:  # noqa: BLE001 — lỗi một lần chạy không được thoát cả CLI
        console.print(f"[red]Lỗi: {type(exc).__name__}: {exc}[/]")
    console.rule(f"[dim]xong sau {time.perf_counter() - start:.1f}s[/]")


def _run_interruptible(loop: asyncio.AbstractEventLoop, coro: Any) -> None:
    """Ctrl+C làm `run_until_complete` ném KeyboardInterrupt nhưng KHÔNG cancel task — phải cancel tay, nếu không nó chạy ngầm tiếp ở lần sau."""
    task = loop.create_task(coro)
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))  # `_execute` tự in "(đã dừng)"


def _handle_command(feature: Feature, cfg: dict[str, Any], line: str) -> bool:
    """Xử lý `/lệnh`; trả True nếu người dùng muốn về menu."""
    cmd, _, arg = line[1:].partition(" ")
    arg = arg.strip()
    if cmd == "b":
        return True
    if cmd == "q":
        raise Quit
    if cmd == "h":
        _help(feature)
    elif cmd == "l":
        console.print(_presets(feature) if feature.presets else "[dim](chức năng này không có preset)[/]")
    elif cmd == "s":
        console.print(_settings_table(feature, cfg) if feature.settings else "[dim](chức năng này không có cài đặt)[/]")
    elif cmd == "set":
        name, _, value = arg.partition(" ")
        if not name and feature.settings:  # `/set` trơ trọi -> chọn bằng phím mũi tên thay vì phải nhớ tên
            name = ui.pick("Chọn cài đặt:", [(s.name, f"{s.name} = {_fmt(cfg[s.name])}  —  {s.help}") for s in feature.settings])
            picked = next(s for s in feature.settings if s.name == name)
            options = _value_choices(picked, cfg)
            if isinstance(picked.default, bool) or picked.choices:
                value = ui.pick(f"{name}:", [(o, o) for o in options], default=_fmt(cfg[name]))
            else:
                value = ui.ask(f"{name} [{_fmt(cfg[name])}]> ") or _fmt(cfg[name])
        setting = next((s for s in feature.settings if s.name == name), None)
        if setting is None:
            console.print(f"[red]Không có cài đặt '{name}'.[/] Có: {', '.join(s.name for s in feature.settings) or '-'}")
        else:
            try:
                cfg[name] = _parse(setting, value.strip())
                console.print(f"[green]{name}[/] = [yellow]{_fmt(cfg[name])}[/]")
            except ValueError as exc:
                console.print(f"[red]Giá trị không hợp lệ:[/] {exc}")
    elif cmd in feature.commands:
        feature.commands[cmd][1]()
    else:
        console.print(f"[red]Lệnh không có:[/] /{cmd} — gõ /h để xem trợ giúp")
    return False


def _feature_screen(feature: Feature, loop: asyncio.AbstractEventLoop) -> None:
    cfg = {s.name: s.default for s in feature.settings}  # cài đặt giữ lại trong suốt phiên, mỗi chức năng một bộ
    console.print(Panel(feature.help, title=f"[bold]{feature.title}[/]", title_align="left"))
    if feature.presets:
        console.print(_presets(feature))
    if feature.settings:
        console.print(_settings_table(feature, cfg))
    console.print("[dim]số = preset · chữ = câu của bạn · /h trợ giúp · /b về menu[/]" if feature.needs_input else "[dim]Enter để chạy · /b về menu[/]")
    while True:
        console.print()
        try:
            line = _ask(f"{feature.key}> ", SlashCompleter(feature, cfg))
        except KeyboardInterrupt:
            console.print()
            return
        if line.split(" ")[0] == "/preset" and feature.presets:  # `/preset` -> chọn trong danh sách; `/preset 2` -> chạy luôn preset 2
            arg = line.partition(" ")[2].strip()
            line = arg if arg.isdigit() else str(ui.pick("Chọn preset:", [(str(i), p.label[:100]) for i, p in enumerate(feature.presets, 1)]))
        if line.startswith("/"):
            if _handle_command(feature, cfg, line):
                return
            continue
        preset = feature.presets[int(line) - 1] if line.isdigit() and 1 <= int(line) <= len(feature.presets) else None
        if preset is None and not line and feature.needs_input:
            continue
        text = preset.text if preset else line
        run_cfg = {**cfg, **(preset.extra if preset else {})}
        _run_interruptible(loop, _execute(feature, text, run_cfg, preset, loop))


def _pick_feature(token: str) -> Feature | None:
    if token.isdigit() and 1 <= int(token) <= len(FEATURES):
        return FEATURES[int(token) - 1]
    return next((f for f in FEATURES if f.key == token), None)


def main() -> None:
    setup_logging("cli")  # hiện log trace của graph (NODE/LLM/TOOL, `agent/tracing.py`); chỉnh mức bằng LOG_LEVEL trong .env
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    direct = _pick_feature(sys.argv[1]) if len(sys.argv) > 1 else None
    if len(sys.argv) > 1 and direct is None:
        console.print(f"[red]Không có chức năng '{sys.argv[1]}'.[/] Có: {', '.join(f.key for f in FEATURES)}")
        return
    try:
        if direct:
            _feature_screen(direct, loop)
        while True:
            console.print()
            try:
                token = str(ui.pick("Chọn chức năng (↑/↓ + Enter, Ctrl+C thoát):", _menu_options()))
            except KeyboardInterrupt:
                console.print()
                break
            except EOFError:
                break
            if token in ("q", "quit", "exit", "/q"):
                break
            feature = _pick_feature(token)
            if feature:
                _feature_screen(feature, loop)
            elif token:
                console.print(f"[red]Không có chức năng '{token}'.[/]")
    except Quit:
        pass
    console.print("[dim]Tạm biệt.[/]")


if __name__ == "__main__":
    main()
