import logging
from typing import Any

from rich import box as rich_box
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, Static

from jujumate import palette
from jujumate.widgets.resource_table import Column

logger = logging.getLogger(__name__)


class NavigableTable(Widget, can_focus=True):
    """Focusable Rich-table view with keyboard navigation.

    Renders using Rich Table (SIMPLE_HEAD box) so the header separator and
    spacing match the App Config view exactly.
    """

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
    ]

    DEFAULT_CSS = """
    NavigableTable {
        height: 1fr;
    }
    NavigableTable #nt-scroll {
        height: 1fr;
        scrollbar-size-vertical: 0;
    }
    NavigableTable #nt-content {
        height: auto;
        padding: 0 1;
    }
    NavigableTable #nt-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """

    class RowSelected(Message):
        """Posted when the user presses Enter on a row."""

        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, columns: list[Column], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._columns = columns
        self._rows: list[tuple] = []
        self._keys: list[str | None] = []
        self._cursor = 0

    def compose(self) -> ComposeResult:
        yield Label("No data available.", id="nt-empty")
        with VerticalScroll(id="nt-scroll", can_focus=False):
            yield Static("", id="nt-content")

    def on_mount(self) -> None:
        self.query_one("#nt-scroll").display = False

    def update_rows(self, rows: list[tuple], keys: list[str] | None = None) -> None:
        self._rows = rows
        self._keys: list[str | None] = keys or [None] * len(rows)  # type: ignore[assignment]
        if self._cursor >= len(rows):
            self._cursor = max(0, len(rows) - 1)
        self._refresh_content()

    def _refresh_content(self) -> None:
        if not self._rows:
            self.query_one("#nt-empty").display = True
            self.query_one("#nt-scroll").display = False
            return
        self.query_one("#nt-empty").display = False
        self.query_one("#nt-scroll").display = True

        t = Table(
            box=rich_box.SIMPLE_HEAD,
            show_header=True,
            expand=True,
            header_style=f"bold {palette.PRIMARY}",
            border_style="dim",
            padding=(0, 1, 1, 1),
        )
        t.add_column("", width=1, no_wrap=True)
        for col in self._columns:
            t.add_column(col.label, width=col.width)
        for i, row in enumerate(self._rows):
            arrow = Text("❯", style=f"bold {palette.PRIMARY}") if i == self._cursor else Text("")
            t.add_row(arrow, *row)

        self.query_one("#nt-content", Static).update(t)
        logger.debug("NavigableTable refreshed: %d rows, cursor=%d", len(self._rows), self._cursor)

    def move_cursor_to_key(self, key: str) -> None:
        """Move the cursor to the row with the given key (no-op if not found)."""
        if key in self._keys:
            self._cursor = self._keys.index(key)
            self._refresh_content()

    def action_cursor_up(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self._refresh_content()

    def action_cursor_down(self) -> None:
        if self._cursor < len(self._rows) - 1:
            self._cursor += 1
            self._refresh_content()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter" and self._rows:
            key = self._keys[self._cursor] if self._keys else None
            if key:
                event.stop()
                self.post_message(NavigableTable.RowSelected(key))
