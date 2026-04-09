from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget

from jujumate.models.entities import CloudInfo
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.resource_table import Column

_COLUMNS = [
    Column("Name", "name"),
    Column("Type", "type", width=12),
]


class CloudsView(Widget):
    class CloudSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield NavigableTable(columns=_COLUMNS, id="clouds-table")

    def update(self, clouds: list[CloudInfo]) -> None:
        rows = [(c.name, c.type) for c in clouds]
        keys = [c.name for c in clouds]
        self.query_one(NavigableTable).update_rows(rows, keys=keys)

    def on_navigable_table_row_selected(self, message: NavigableTable.RowSelected) -> None:
        message.stop()
        self.post_message(self.CloudSelected(name=message.key))
