"""Modal screen that streams live Juju model logs."""

import asyncio
import logging
from collections import deque

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog, Rule

from jujumate import palette
from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import LogEntry

logger = logging.getLogger(__name__)

_LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR"]

_LEVEL_COLORS: dict[str, str] = {
    "TRACE": palette.MUTED,
    "DEBUG": palette.LINK,
    "INFO": palette.SUCCESS,
    "WARNING": palette.WARNING,
    "ERROR": palette.ERROR,
    "FATAL": palette.ERROR,
    "CRITICAL": palette.ERROR,
}


def _append_highlighted(t: Text, value: str, needle: str, base_style: str) -> None:
    """Append value to t, highlighting case-insensitive occurrences of needle."""
    if not needle:
        t.append(value, style=base_style)
        return
    lower_val = value.lower()
    lower_needle = needle.lower()
    pos = 0
    nlen = len(needle)
    while pos <= len(value):
        idx = lower_val.find(lower_needle, pos)
        if idx == -1:
            t.append(value[pos:], style=base_style)
            break
        t.append(value[pos:idx], style=base_style)
        t.append(value[idx : idx + nlen], style=f"bold reverse {palette.WARNING}")
        pos = idx + nlen


_MAX_BUFFER = 2000


class LogScreen(ModalScreen):
    """Full-screen modal that streams live logs for the selected model."""

    BINDINGS = [
        Binding("escape", "close_or_clear", "Close", show=False),
        Binding("l", "cycle_level", "Level ↕", show=True),
        Binding("slash", "focus_filter", "Filter", show=True, priority=True),
        Binding("y", "copy_logs", "Copy", show=True),
        Binding("end", "scroll_end", "↓ Bottom", show=True),
        Binding("enter", "insert_separator", "── separator", show=True),
    ]

    DEFAULT_CSS = """
    LogScreen {
        align: center middle;
    }
    LogScreen #log-outer {
        width: 98%;
        height: 95%;
        background: $surface;
        border: round $accent;
        border-title-color: $accent;
        border-title-style: bold;
    }
    LogScreen #log-header {
        height: 3;
        background: $panel;
        padding: 1 1 0 1;
    }
    LogScreen #log-header Label {
        height: 1;
    }
    LogScreen #log-level-label {
        color: $accent;
        text-style: bold;
    }
    LogScreen #log-model-label {
        color: $text-muted;
    }
    LogScreen #log-live-indicator {
        width: 1fr;
        content-align: right middle;
    }
    LogScreen #log-divider {
        color: $accent;
        margin: 0;
    }
    LogScreen #log-filter-bar {
        height: 1;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    LogScreen #log-filter-bar.visible {
        display: block;
        height: 3;
        padding: 0 1;
    }
    LogScreen #log-filter {
        background: $surface;
        border: solid $accent;
        height: 3;
        padding: 0 1;
    }
    LogScreen #log-richlog {
        height: 1fr;
        background: $surface;
        padding: 0 1;
        scrollbar-size-vertical: 0;
    }
    LogScreen #log-hint {
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    LogScreen .hint-key {
        color: $accent;
        height: 1;
    }
    LogScreen .hint-item {
        color: $text-muted;
        height: 1;
    }
    LogScreen .hint-sep {
        color: $accent;
        height: 1;
    }
    """

    def __init__(self, controller: str, model: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._controller = controller
        self._model = model
        self._level_idx = 2  # default: INFO
        self._filter_text = ""
        self._buffer: deque[LogEntry] = deque(maxlen=_MAX_BUFFER)
        self._blink_state = False

    @property
    def _level(self) -> str:
        return _LEVELS[self._level_idx]

    def compose(self) -> ComposeResult:
        with Vertical(id="log-outer"):
            with Horizontal(id="log-header"):
                yield Label(f"Logs — {self._controller}:{self._model}", id="log-model-label")
                yield Label(f"  │  Level: {self._level}", id="log-level-label")
                yield Label("● LIVE", id="log-live-indicator")
            yield Rule(id="log-divider")
            with Horizontal(id="log-filter-bar"):
                yield Label("Filter: ")
                yield Input(placeholder="entity or message…", id="log-filter")
            yield RichLog(
                id="log-richlog",
                max_lines=_MAX_BUFFER,
                auto_scroll=True,
                highlight=False,
                markup=False,
                wrap=True,
            )
            with Horizontal(id="log-hint"):
                yield Label("l", classes="hint-key")
                yield Label(": level", classes="hint-item")
                yield Label("  |  ", classes="hint-sep")
                yield Label("/", classes="hint-key")
                yield Label(": filter", classes="hint-item")
                yield Label("  |  ", classes="hint-sep")
                yield Label("y", classes="hint-key")
                yield Label(": copy", classes="hint-item")
                yield Label("  |  ", classes="hint-sep")
                yield Label("Enter", classes="hint-key")
                yield Label(": separator", classes="hint-item")
                yield Label("  |  ", classes="hint-sep")
                yield Label("End", classes="hint-key")
                yield Label(": ↓ bottom", classes="hint-item")
                yield Label("  |  ", classes="hint-sep")
                yield Label("Esc", classes="hint-key")
                yield Label(": close", classes="hint-item")

    def on_mount(self) -> None:
        outer = self.query_one("#log-outer")
        outer.border_title = "Live Logs"
        richlog = self.query_one("#log-richlog", RichLog)
        richlog.write(Text("Connecting to log stream…", style=palette.MUTED))
        self.set_interval(0.8, self._blink_live_indicator)
        self._start_stream()

    def _blink_live_indicator(self) -> None:
        self._blink_state = not self._blink_state
        try:
            indicator = self.query_one("#log-live-indicator", Label)
            if self._blink_state:
                indicator.update(Text("● LIVE", style=f"bold {palette.SUCCESS}"))
            else:
                indicator.update(Text("○ LIVE", style=palette.MUTED))
        except Exception:
            pass

    def on_unmount(self) -> None:
        # Workers are automatically cancelled by Textual on unmount
        pass

    @work(exclusive=True, exit_on_error=False)
    async def _start_stream(self) -> None:
        richlog = self.query_one("#log-richlog", RichLog)
        richlog.clear()
        self._buffer.clear()
        self._update_level_label()
        try:
            async with JujuClient(self._controller) as client:
                async for entry in client.stream_logs(self._model, level=self._level):
                    self._buffer.append(entry)
                    if self._matches_filter(entry):
                        richlog.write(self._format_entry(entry))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Log stream failed for %s:%s", self._controller, self._model)
            self.notify(str(exc), title="Log stream error", severity="error")

    def _format_entry(self, entry: LogEntry) -> Text:
        color = _LEVEL_COLORS.get(entry.level, palette.MUTED)
        needle = self._filter_text
        t = Text(overflow="fold")
        _append_highlighted(t, entry.entity, needle, palette.MUTED)
        t.append(" ", style=palette.MUTED)
        t.append(entry.timestamp, style=palette.MUTED)
        t.append(" ", style=palette.MUTED)
        t.append(entry.level, style=color)
        t.append(" ", style=palette.MUTED)
        t.append(entry.module, style=palette.MUTED)
        t.append(" ", style=palette.MUTED)
        _append_highlighted(t, entry.message, needle, "default")
        return t

    def _matches_filter(self, entry: LogEntry) -> bool:
        if not self._filter_text:
            return True
        needle = self._filter_text.lower()
        return needle in entry.entity.lower() or needle in entry.message.lower()

    def _update_level_label(self) -> None:
        label = self.query_one("#log-level-label", Label)
        color = _LEVEL_COLORS.get(self._level, palette.MUTED)
        label.update(Text(f"  │  Level: {self._level}", style=f"bold {color}"))

    def _rerender_buffer(self) -> None:
        richlog = self.query_one("#log-richlog", RichLog)
        richlog.clear()
        for entry in self._buffer:
            if self._matches_filter(entry):
                richlog.write(self._format_entry(entry))

    def action_focus_filter(self) -> None:
        bar = self.query_one("#log-filter-bar")
        filter_input = self.query_one("#log-filter", Input)
        if "visible" in bar.classes:
            # Already open: priority binding consumed the slash — re-insert it manually
            filter_input.insert_text_at_cursor("/")
        else:
            bar.add_class("visible")
            self.call_after_refresh(filter_input.focus)

    def action_close_or_clear(self) -> None:
        """Esc: clear filter when in filter mode, otherwise dismiss."""
        filter_input = self.query_one("#log-filter", Input)
        if self.focused is filter_input:
            filter_input.value = ""
            self.query_one("#log-filter-bar").remove_class("visible")
            self.query_one("#log-richlog", RichLog).focus()
        else:
            self.dismiss()

    def action_cycle_level(self) -> None:
        self._level_idx = (self._level_idx + 1) % len(_LEVELS)
        self._start_stream()  # restarts the worker at the new level

    def action_scroll_end(self) -> None:
        richlog = self.query_one("#log-richlog", RichLog)
        richlog.auto_scroll = True
        richlog.scroll_end(animate=False)

    def action_insert_separator(self) -> None:
        if self.focused is self.query_one("#log-filter", Input):
            return
        self.query_one("#log-richlog", RichLog).write(Text(""))

    def action_copy_logs(self) -> None:
        """Copy selected text (or all visible log lines) to clipboard."""
        richlog = self.query_one("#log-richlog", RichLog)
        sel = richlog.text_selection
        if sel is not None:
            result = richlog.get_selection(sel)
            if result is not None:
                self.app.copy_to_clipboard(result[0])
                self.notify("Selection copied to clipboard")
                return
        lines = [
            f"{e.entity} {e.timestamp} {e.level} {e.module} {e.message}"
            for e in self._buffer
            if self._matches_filter(e)
        ]
        self.app.copy_to_clipboard("\n".join(lines))
        self.notify(f"{len(lines)} lines copied to clipboard")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "log-filter":
            self._filter_text = event.value
            self._rerender_buffer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "log-filter":
            self.query_one("#log-richlog", RichLog).focus()
