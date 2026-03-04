import logging
from typing import Any

from rich import box as rich_box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Static

from jujumate import palette
from jujumate.models.entities import AppConfigEntry, AppInfo

logger = logging.getLogger(__name__)

_C_KEY = "bold white"
_C_META = "dim"


def _colored_status(status: str) -> Text:
    colors = {
        "active": palette.SUCCESS, "blocked": palette.ERROR,
        "error": palette.ERROR, "waiting": palette.WARNING, "maintenance": palette.WARNING,
    }
    color = colors.get(status.strip().lower(), "")
    return Text(status, style=color) if color else Text(status)


def _build_config_renderable(app: AppInfo, entries: list[AppConfigEntry]) -> Group:
    """Build a Rich Group showing app config with header panel + config table."""
    # ── Header panel ─────────────────────────────────────────────────────────
    meta = Table(box=None, show_header=False, padding=(0, 1), expand=False)
    meta.add_column("k", style=_C_META, no_wrap=True)
    meta.add_column("v")
    meta.add_row("charm", app.charm)
    meta.add_row("channel", app.channel)
    meta.add_row("rev", str(app.revision))
    meta.add_row("status", _colored_status(app.status))
    header = Panel(
        meta,
        title=Text(app.name, style=f"bold {palette.PRIMARY}"),
        border_style=palette.PRIMARY,
        expand=True,
        padding=(0, 1),
    )

    # ── Config table ──────────────────────────────────────────────────────────
    changed = sorted([e for e in entries if not e.is_default], key=lambda x: x.key)
    defaults = sorted([e for e in entries if e.is_default], key=lambda x: x.key)

    t = Table(
        box=rich_box.SIMPLE_HEAD,
        show_header=True,
        expand=True,
        header_style=f"bold {palette.PRIMARY}",
        padding=(0, 1, 1, 1),
    )
    t.add_column("Key", no_wrap=True)
    t.add_column("Type", style="dim", width=10, no_wrap=True)
    t.add_column("Value", overflow="fold")
    t.add_column("Description", style="dim", overflow="fold")

    for e in changed:
        key_text = Text()
        key_text.append("★ ", style=f"bold {palette.PRIMARY}")
        key_text.append(e.key, style=f"bold {palette.PRIMARY}")
        value_text = Text(e.value, style=f"bold {palette.PRIMARY}")
        if e.default and e.default != e.value:
            value_text.append(f"  [default: {e.default}]", style="dim")
        t.add_row(key_text, e.type, value_text, e.description)

    for e in defaults:
        t.add_row(
            Text(e.key, style=_C_KEY),
            e.type,
            Text(e.value, style="dim"),
            Text(e.description, style="dim"),
        )

    if not entries:
        t.add_row(Text("<no config>", style=_C_META), "", "", "")

    return Group(header, t)


def _format_plain_text(app: AppInfo, entries: list[AppConfigEntry]) -> str:
    """Format app config as plain text for clipboard."""
    lines = [
        f"app: {app.name}",
        f"charm: {app.charm}  channel: {app.channel}  rev: {app.revision}",
        "",
        "# user-set values",
    ]
    changed = sorted([e for e in entries if not e.is_default], key=lambda x: x.key)
    defaults = sorted([e for e in entries if e.is_default], key=lambda x: x.key)
    for e in changed:
        suffix = f"  # default: {e.default}" if e.default and e.default != e.value else ""
        lines.append(f"  {e.key}: {e.value}{suffix}")
    if not changed:
        lines.append("  (none)")
    lines += ["", "# default values"]
    for e in defaults:
        lines.append(f"  {e.key}: {e.value}")
    return "\n".join(lines)


class AppConfigView(Widget):
    """Shows the configuration for a selected application."""

    BINDINGS = [
        Binding("y", "copy_to_clipboard", "Copy config", show=False),
    ]

    DEFAULT_CSS = """
    AppConfigView {
        height: 1fr;
    }
    AppConfigView #ac-scroll {
        height: 1fr;
        scrollbar-size-vertical: 0;
    }
    AppConfigView #ac-content {
        height: auto;
        padding: 0 1;
    }
    AppConfigView #ac-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_app: AppInfo | None = None
        self._current_entries: list[AppConfigEntry] = []

    def compose(self) -> ComposeResult:
        yield Label(
            "No app selected — press Enter on an application to see its config.",
            id="ac-empty",
        )
        with VerticalScroll(id="ac-scroll"):
            yield Static("", id="ac-content")

    def on_mount(self) -> None:
        self.query_one("#ac-scroll").display = False

    def update(self, app: AppInfo, entries: list[AppConfigEntry]) -> None:
        """Populate the view with app config."""
        self._current_app = app
        self._current_entries = entries
        renderable = _build_config_renderable(app, entries)
        self.query_one("#ac-content", Static).update(renderable)
        self.query_one("#ac-empty").display = False
        self.query_one("#ac-scroll").display = True
        logger.debug("AppConfigView updated: app '%s', %d entries", app.name, len(entries))

    def show_loading(self, app: AppInfo) -> None:
        """Show a loading state while config is being fetched."""
        self.query_one("#ac-empty").display = True
        self.query_one("#ac-empty", Label).update(f"Fetching config for {app.name}…")
        self.query_one("#ac-scroll").display = False

    def show_error(self, app: AppInfo, error: str) -> None:
        """Show an error state when the fetch failed."""
        self.query_one("#ac-empty").display = True
        self.query_one("#ac-empty", Label).update(
            f"[red]Error fetching config for {app.name}:\n{error}[/red]"
        )
        self.query_one("#ac-scroll").display = False

    def action_copy_to_clipboard(self) -> None:
        if not self._current_app:
            self.notify("No config to copy", severity="warning")
            return
        text = _format_plain_text(self._current_app, self._current_entries)
        self.app.copy_to_clipboard(text)
        self.notify("App config copied to clipboard")
