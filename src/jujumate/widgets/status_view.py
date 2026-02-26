import logging
from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label

from jujumate.models.entities import AppInfo, RelationInfo, UnitInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

_APP_COLUMNS = [
    Column("Name", "s-app-name"),
    Column("Version", "s-app-version", width=10),
    Column("Status", "s-app-status", width=12),
    Column("Scale", "s-app-scale", width=6),
    Column("Charm", "s-app-charm", width=18),
    Column("Channel", "s-app-channel", width=14),
    Column("Rev", "s-app-rev", width=5),
    Column("Address", "s-app-addr", width=16),
    Column("Exposed", "s-app-exposed", width=8),
    Column("Message", "s-app-message"),
]

_UNIT_COLUMNS = [
    Column("Unit", "s-unit-name"),
    Column("Workload", "s-unit-wl", width=12),
    Column("Agent", "s-unit-agent", width=12),
    Column("Machine", "s-unit-machine", width=10),
    Column("Address", "s-unit-addr", width=16),
]

_REL_COLUMNS = [
    Column("Provider", "s-rel-provider"),
    Column("Requirer", "s-rel-requirer"),
    Column("Interface", "s-rel-iface", width=16),
    Column("Type", "s-rel-type", width=10),
]


class StatusView(Widget):
    """Displays a juju-status–style overview for the selected model."""

    DEFAULT_CSS = """
    StatusView {
        height: 1fr;
    }
    StatusView .section-label {
        padding: 1 2 0 2;
        text-style: bold;
        color: $accent;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Label("Applications", classes="section-label")
            yield ResourceTable(columns=_APP_COLUMNS, id="status-apps-table")
            yield Label("Units", classes="section-label")
            yield ResourceTable(columns=_UNIT_COLUMNS, id="status-units-table")
            yield Label("Relations", classes="section-label")
            yield ResourceTable(columns=_REL_COLUMNS, id="status-rels-table")

    def update_apps(self, apps: list[AppInfo]) -> None:
        rows = [
            (
                a.name,
                a.version,
                a.status,
                str(a.unit_count),
                a.charm,
                a.channel,
                str(a.revision),
                a.address,
                "yes" if a.exposed else "no",
                a.message,
            )
            for a in apps
        ]
        self.query_one("#status-apps-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView apps updated: %d rows", len(rows))

    def update_units(self, units: list[UnitInfo]) -> None:
        rows = [
            (u.name, u.workload_status, u.agent_status, u.machine, u.address)
            for u in units
        ]
        self.query_one("#status-units-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView units updated: %d rows", len(rows))

    def update_relations(self, relations: list[RelationInfo]) -> None:
        rows = [(r.provider, r.requirer, r.interface, r.type) for r in relations]
        self.query_one("#status-rels-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView relations updated: %d rows", len(rows))
