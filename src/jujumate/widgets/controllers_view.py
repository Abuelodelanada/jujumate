import logging
from typing import Any

from textual.app import ComposeResult
from textual.widget import Widget

from jujumate.models.entities import ControllerInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

_COLUMNS = [
    Column("Name", "name"),
    Column("Cloud", "cloud", width=14),
    Column("Region", "region", width=14),
    Column("Juju Version", "version", width=14),
    Column("Models", "models", width=8),
]


class ControllersView(Widget):
    DEFAULT_CSS = "ControllersView { height: 1fr; }"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield ResourceTable(columns=_COLUMNS, id="controllers-table")

    def update(self, controllers: list[ControllerInfo]) -> None:
        rows = [
            (c.name, c.cloud, c.region, c.juju_version, str(c.model_count)) for c in controllers
        ]
        self.query_one(ResourceTable).update_rows(rows)
        logger.debug("ControllersView updated with %d controllers", len(controllers))
