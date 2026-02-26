import logging
from typing import Any

from textual.app import ComposeResult
from textual.widget import Widget

from jujumate.models.entities import CloudInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

_COLUMNS = [
    Column("Name", "name"),
    Column("Type", "type", width=12),
    Column("Regions", "regions", width=20),
    Column("Credentials", "credentials", width=20),
]


class CloudsView(Widget):
    DEFAULT_CSS = "CloudsView { height: 1fr; }"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield ResourceTable(columns=_COLUMNS, id="clouds-table")

    def update(self, clouds: list[CloudInfo]) -> None:
        rows = [
            (
                c.name,
                c.type,
                ", ".join(c.regions) if c.regions else "—",
                ", ".join(c.credentials) if c.credentials else "—",
            )
            for c in clouds
        ]
        self.query_one(ResourceTable).update_rows(rows)
        logger.debug("CloudsView updated with %d clouds", len(clouds))
