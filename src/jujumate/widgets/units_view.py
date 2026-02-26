import logging
from typing import Any

from textual.app import ComposeResult
from textual.widget import Widget

from jujumate.models.entities import UnitInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

_COLUMNS = [
    Column("Name", "name"),
    Column("App", "app", width=14),
    Column("Machine/Pod", "machine", width=12),
    Column("Workload", "workload", width=12),
    Column("Agent", "agent", width=12),
    Column("Address", "address", width=16),
]


class UnitsView(Widget):
    DEFAULT_CSS = "UnitsView { height: 1fr; }"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield ResourceTable(columns=_COLUMNS, id="units-table")

    def update(self, units: list[UnitInfo]) -> None:
        rows = [
            (u.name, u.app, u.machine, u.workload_status, u.agent_status, u.address) for u in units
        ]
        self.query_one(ResourceTable).update_rows(rows)
        logger.debug("UnitsView updated with %d units", len(units))
