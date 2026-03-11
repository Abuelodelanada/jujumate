from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable

from jujumate import palette
from jujumate.models.entities import AppInfo
from jujumate.widgets.resource_table import Column, ResourceTable

_COLUMNS = [
    Column("Name", "name"),
    Column("Model", "model", width=12),
    Column("Charm", "charm", width=16),
    Column("Channel", "channel", width=14),
    Column("Rev", "rev", width=6),
    Column("Units", "units", width=6),
    Column("Status", "status", width=12),
    Column("Message", "message"),
]


class AppsView(Widget):
    DEFAULT_CSS = (Path(__file__).parent / "apps_view.tcss").read_text()

    class AppSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield ResourceTable(columns=_COLUMNS, id="apps-table")

    def update(self, apps: list[AppInfo]) -> None:
        rows = [
            (
                a.name,
                a.model,
                a.charm,
                a.channel,
                Text(str(a.revision), style=f"bold {palette.WARNING}")
                if a.can_upgrade_to
                else str(a.revision),
                str(a.unit_count),
                a.status,
                a.message,
            )
            for a in apps
        ]
        keys = [f"{a.model}/{a.name}" for a in apps]
        self.query_one(ResourceTable).update_rows(rows, keys=keys)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        if event.row_key.value:
            self.post_message(self.AppSelected(name=str(event.row_key.value)))
