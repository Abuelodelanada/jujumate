import logging
from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label

from jujumate.models.entities import AppInfo, OfferInfo, RelationInfo, UnitInfo
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

_UNIT_COLUMNS_K8S = [
    Column("Unit", "s-unit-name"),
    Column("Workload", "s-unit-wl", width=12),
    Column("Agent", "s-unit-agent", width=12),
    Column("Address", "s-unit-addr", width=16),
    Column("Ports", "s-unit-ports", width=16),
    Column("Message", "s-unit-msg"),
]

_UNIT_COLUMNS_IAAS = [
    Column("Unit", "s-unit-name"),
    Column("Workload", "s-unit-wl", width=12),
    Column("Agent", "s-unit-agent", width=12),
    Column("Machine", "s-unit-machine", width=10),
    Column("Public Address", "s-unit-pubaddr", width=18),
    Column("Ports", "s-unit-ports", width=16),
    Column("Message", "s-unit-msg"),
]

_OFFER_COLUMNS = [
    Column("Offer", "s-offer-name"),
    Column("Application", "s-offer-app", width=16),
    Column("Charm", "s-offer-charm", width=18),
    Column("Rev", "s-offer-rev", width=5),
    Column("Connected", "s-offer-conn", width=10),
    Column("Endpoint", "s-offer-ep", width=20),
    Column("Interface", "s-offer-iface", width=22),
    Column("Role", "s-offer-role", width=10),
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
            yield ResourceTable(columns=_UNIT_COLUMNS_IAAS, id="status-units-table")
            yield Label("Offers", classes="section-label", id="status-offers-label")
            yield ResourceTable(columns=_OFFER_COLUMNS, id="status-offers-table")
            yield Label("Relations", classes="section-label")
            yield ResourceTable(columns=_REL_COLUMNS, id="status-rels-table")

    def on_mount(self) -> None:
        self.query_one("#status-offers-label").display = False
        self.query_one("#status-offers-table").display = False

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

    def update_units(self, units: list[UnitInfo], is_kubernetes: bool = False) -> None:
        table = self.query_one("#status-units-table", ResourceTable)
        if is_kubernetes:
            table.reset_columns(_UNIT_COLUMNS_K8S)
            rows = [
                (u.name, u.workload_status, u.agent_status, u.address, u.ports, u.message)
                for u in units
            ]
        else:
            table.reset_columns(_UNIT_COLUMNS_IAAS)
            rows = [
                (u.name, u.workload_status, u.agent_status, u.machine, u.public_address, u.ports, u.message)
                for u in units
            ]
        table.update_rows(rows)
        logger.debug("StatusView units updated: %d rows (k8s=%s)", len(rows), is_kubernetes)

    def update_offers(self, offers: list[OfferInfo]) -> None:
        has_offers = bool(offers)
        self.query_one("#status-offers-label").display = has_offers
        self.query_one("#status-offers-table").display = has_offers
        rows = [
            (o.name, o.application, o.charm, str(o.rev), o.connected, o.endpoint, o.interface, o.role)
            for o in offers
        ]
        self.query_one("#status-offers-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView offers updated: %d rows", len(rows))

    def update_relations(self, relations: list[RelationInfo]) -> None:
        rows = [(r.provider, r.requirer, r.interface, r.type) for r in relations]
        self.query_one("#status-rels-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView relations updated: %d rows", len(rows))
