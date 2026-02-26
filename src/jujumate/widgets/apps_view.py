import logging
from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable

from jujumate.models.entities import AppInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

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
    DEFAULT_CSS = "AppsView { height: 1fr; }"

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
                str(a.revision),
                str(a.unit_count),
                a.status,
                a.message,
            )
            for a in apps
        ]
        keys = [f"{a.model}/{a.name}" for a in apps]
        self.query_one(ResourceTable).update_rows(rows, keys=keys)
        logger.debug("AppsView updated with %d apps", len(apps))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        if event.row_key.value:
            self.post_message(self.AppSelected(name=str(event.row_key.value)))
