import logging
from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget

from jujumate.models.entities import ModelInfo
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.resource_table import Column

logger = logging.getLogger(__name__)

_COLUMNS = [
    Column("Name", "name"),
    Column("Controller", "controller", width=16),
    Column("Cloud/Region", "cloud_region", width=18),
    Column("Status", "status", width=12),
    Column("Machines", "machines", width=10),
    Column("Apps", "apps", width=6),
]


class ModelsView(Widget):
    DEFAULT_CSS = "ModelsView { height: 1fr; }"

    class ModelSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield NavigableTable(columns=_COLUMNS, id="models-table")

    def update(self, models: list[ModelInfo]) -> None:
        rows = [
            (
                m.name,
                m.controller,
                f"{m.cloud}/{m.region}" if m.region else m.cloud,
                m.status,
                str(m.machine_count),
                str(m.app_count),
            )
            for m in models
        ]
        keys = [f"{m.controller}/{m.name}" for m in models]
        self.query_one(NavigableTable).update_rows(rows, keys=keys)
        logger.debug("ModelsView updated with %d models", len(models))

    def select_model(self, controller: str, model: str) -> None:
        """Position the cursor on the given controller/model row."""
        self.query_one(NavigableTable).move_cursor_to_key(f"{controller}/{model}")

    def on_navigable_table_row_selected(self, message: NavigableTable.RowSelected) -> None:
        message.stop()
        self.post_message(self.ModelSelected(name=message.key))
