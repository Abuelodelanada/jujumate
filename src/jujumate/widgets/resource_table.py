import logging
from dataclasses import dataclass
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Label

logger = logging.getLogger(__name__)


@dataclass
class Column:
    label: str
    key: str
    width: int | None = None


class ResourceTable(Widget):
    """Generic reusable DataTable for displaying Juju resources."""

    class TableFocused(Message):
        """Posted (bubbling) when the internal DataTable gains focus."""

        def __init__(self, resource_table: "ResourceTable") -> None:
            super().__init__()
            self.resource_table = resource_table

    DEFAULT_CSS = """
    ResourceTable {
        height: 1fr;
    }
    ResourceTable Label {
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(self, columns: list[Column], *args: Any, cursor: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._columns = columns
        self._cursor = cursor
        self._is_loading = False

    def compose(self) -> ComposeResult:
        cursor_type = "row" if self._cursor else "none"
        resource_table = self

        class _FocusableTable(DataTable):
            def _on_focus(self, event: events.Focus) -> None:
                super()._on_focus(event)
                resource_table.post_message(ResourceTable.TableFocused(resource_table))

        table = _FocusableTable(cursor_type=cursor_type, zebra_stripes=False, cursor_background_priority="css")
        for col in self._columns:
            table.add_column(col.label, key=col.key, width=col.width)
        yield table
        yield Label("No data available.", id="empty-label")

    def on_mount(self) -> None:
        self.query_one("#empty-label").display = False

    def reset_columns(self, columns: list[Column]) -> None:
        """Replace all columns (and clear rows) with a new column set."""
        self._columns = columns
        table = self.query_one(DataTable)
        table.clear(columns=True)
        for col in self._columns:
            table.add_column(col.label, key=col.key, width=col.width)

    def update_rows(
        self,
        rows: list[tuple],
        keys: list[str] | None = None,
        heights: list[int] | None = None,
    ) -> None:
        """Replace all table rows. Each tuple must match the column order."""
        table = self.query_one(DataTable)
        table.clear()
        if rows:
            for i, row in enumerate(rows):
                key = keys[i] if keys else None
                height = heights[i] if heights else 1
                table.add_row(*row, key=key, height=height)
            self.query_one("#empty-label").display = False
            logger.debug("ResourceTable updated with %d rows", len(rows))
        else:
            self.query_one("#empty-label").display = True
            logger.debug("ResourceTable has no rows to display")

    def set_loading(self, loading: bool) -> None:
        """Show or hide a loading indicator."""
        self._is_loading = loading
        self.loading = loading
