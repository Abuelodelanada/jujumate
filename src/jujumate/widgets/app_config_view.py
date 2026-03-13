from pathlib import Path
from typing import Any

from rich import box as rich_box
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Rule, Static

from jujumate import palette
from jujumate.models.entities import AppConfigEntry, AppInfo

_C_KEY = "bold white"
_C_META = "dim"


def _status_color(status: str) -> str:
    return {
        "active": palette.SUCCESS,
        "blocked": palette.ERROR,
        "error": palette.ERROR,
        "waiting": palette.WARNING,
        "maintenance": palette.WARNING,
    }.get(status, "")


def _meta_markup(app: AppInfo) -> str:
    """Build Rich markup for the metadata header (charm, channel, rev, status)."""
    fields = [
        ("Charm", app.charm),
        ("Channel", app.channel or "—"),
        ("Rev", str(app.revision)),
        ("Status", app.status),
    ]
    col_width = max(len(f) for f, _ in fields) + 2
    lines = []
    for field, value in fields:
        label = f"{field}:".ljust(col_width)
        if field == "Status":
            color = _status_color(value.strip().lower())
            styled = f"[{color}]{value}[/]" if color else value
        else:
            styled = value
        lines.append(f"[bold]{label}[/bold]{styled}")
    return "\n".join(lines)


def _build_config_renderable(entries: list[AppConfigEntry]) -> Table:
    """Build the config key/value table."""
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

    return t


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

    DEFAULT_CSS = (Path(__file__).parent / "app_config_view.tcss").read_text()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_app: AppInfo | None = None
        self._current_entries: list[AppConfigEntry] = []

    def compose(self) -> ComposeResult:
        yield Label(
            "No app selected — press Enter on an application to see its config.",
            id="ac-empty",
        )
        with Vertical(id="ac-panel"):
            yield Static("", id="ac-meta-content")
            yield Rule()
            with VerticalScroll(id="ac-scroll"):
                yield Static("", id="ac-content")

    def on_mount(self) -> None:
        self.query_one("#ac-panel").display = False

    def update(self, app: AppInfo, entries: list[AppConfigEntry]) -> None:
        """Populate the view with app config."""
        self._current_app = app
        self._current_entries = entries
        self.query_one("#ac-meta-content", Static).update(_meta_markup(app))
        renderable = _build_config_renderable(entries)
        self.query_one("#ac-content", Static).update(renderable)
        self.query_one("#ac-empty").display = False
        self.query_one("#ac-panel").display = True

    def show_loading(self, app: AppInfo) -> None:
        """Show a loading state while config is being fetched."""
        self.query_one("#ac-empty").display = True
        self.query_one("#ac-empty", Label).update(f"Fetching config for {app.name}…")
        self.query_one("#ac-panel").display = False

    def show_error(self, app: AppInfo, error: str) -> None:
        """Show an error state when the fetch failed."""
        self.query_one("#ac-empty").display = True
        self.query_one("#ac-empty", Label).update(
            f"[red]Error fetching config for {app.name}:\n{error}[/red]"
        )
        self.query_one("#ac-panel").display = False

    def action_copy_to_clipboard(self) -> None:
        if not self._current_app:
            self.notify("No config to copy", severity="warning")
            return
        text = _format_plain_text(self._current_app, self._current_entries)
        self.app.copy_to_clipboard(text)
        self.notify("App config copied to clipboard")
