import logging
from typing import Any

from textual.app import ComposeResult
from textual.widget import Widget

from jujumate.models.entities import ModelInfo
from jujumate.widgets.resource_table import Column, ResourceTable

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield ResourceTable(columns=_COLUMNS, id="models-table")

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
        self.query_one(ResourceTable).update_rows(rows)
        logger.debug("ModelsView updated with %d models", len(models))
