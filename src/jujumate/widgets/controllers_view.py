from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget

from jujumate.models.entities import ControllerInfo
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.resource_table import Column

_COLUMNS = [
    Column("Name", "name"),
    Column("Cloud", "cloud", width=14),
    Column("Region", "region", width=14),
    Column("Juju Version", "version", width=14),
    Column("Models", "models", width=8),
]

class ControllersView(Widget):
    DEFAULT_CSS = "ControllersView { height: 1fr; }"

    class ControllerSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield NavigableTable(columns=_COLUMNS, id="controllers-table")

    def update(self, controllers: list[ControllerInfo]) -> None:
        rows = [
            (c.name, c.cloud, c.region, c.juju_version, str(c.model_count)) for c in controllers
        ]
        keys = [c.name for c in controllers]
        self.query_one(NavigableTable).update_rows(rows, keys=keys)

    def on_navigable_table_row_selected(self, message: NavigableTable.RowSelected) -> None:
        message.stop()
        self.post_message(self.ControllerSelected(name=message.key))
