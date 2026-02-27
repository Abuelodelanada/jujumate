import logging
import textwrap
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from jujumate.models.entities import AppInfo, MachineInfo, OfferInfo, RelationInfo, UnitInfo
from jujumate.widgets.resource_table import Column, ResourceTable

logger = logging.getLogger(__name__)

_STATUS_COLORS: dict[str, str] = {
    "active": "#26A269",
    "idle": "#26A269",
    "started": "#26A269",
    "blocked": "#FF5555",
    "error": "#FF5555",
    "maintenance": "#EFB73E",
    "waiting": "#EFB73E",
    "executing": "#EFB73E",
}


def _colored_status(status: str) -> Text:
    """Return a Rich Text object with the status colored by severity."""
    color = _STATUS_COLORS.get(status.lower(), "")
    if color:
        return Text(status, style=color)
    return Text(status)


def _colored_ip(address: str) -> Text:
    """Color an IP address in Ubuntu Cyan."""
    if address:
        return Text(address, style="#19B6EE")
    return Text(address)


def _colored_relation(endpoint: str) -> Text:
    """Color the :rel_name part of an APP:REL endpoint in Ubuntu Orange."""
    if ":" in endpoint:
        app, rel = endpoint.split(":", 1)
        text = Text(app)
        text.append(":", style="#19B6EE")
        text.append(rel, style="#19B6EE")
        return text
    return Text(endpoint)

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

_MACHINE_COLUMNS = [
    Column("Machine", "s-mach-id"),
    Column("State", "s-mach-state", width=12),
    Column("Address", "s-mach-addr", width=18),
    Column("Inst id", "s-mach-inst", width=22),
    Column("Base", "s-mach-base", width=16),
    Column("AZ", "s-mach-az", width=14),
    Column("Message", "s-mach-msg"),
]


_MSG_WRAP_WIDTH = 45


def _wrap_msg(text: str) -> tuple[str, int]:
    """Wrap a message string. Returns (wrapped_text, line_count)."""
    if not text:
        return text, 1
    lines = textwrap.wrap(text, width=_MSG_WRAP_WIDTH)
    return "\n".join(lines) if lines else text, max(len(lines), 1)


def _group_units(units: list) -> list:
    """Return units with subordinates placed immediately after their principal."""
    principals = [u for u in units if not u.subordinate_of]
    result = []
    for principal in principals:
        result.append(principal)
        result.extend(u for u in units if u.subordinate_of == principal.name)
    # Append any orphan subordinates (principal not in this view) at the end
    known_principals = {p.name for p in principals}
    result.extend(u for u in units if u.subordinate_of and u.subordinate_of not in known_principals)
    return result


class _TrackedScroll(VerticalScroll):
    """VerticalScroll that notifies its parent when scroll_y changes."""

    def watch_scroll_y(self, value: float) -> None:
        if isinstance(self.parent, StatusView):
            self.parent._update_scroll_indicator()


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
    StatusView ResourceTable {
        height: auto;
        border: none;
    }
    StatusView DataTable {
        height: auto;
        border: none;
        scrollbar-size: 0 0;
        overflow-x: hidden;
    }
    StatusView VerticalScroll {
        scrollbar-size: 0 0;
    }
    StatusView #scroll-indicator {
        dock: bottom;
        height: 1;
        width: 100%;
        text-align: center;
        text-style: dim;
        color: $text-muted;
    }
    """

    _show_more: reactive[bool] = reactive(False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        with _TrackedScroll():
            yield Label("Applications", classes="section-label")
            yield ResourceTable(columns=_APP_COLUMNS, id="status-apps-table", cursor=False)
            yield Label("Units", classes="section-label")
            yield ResourceTable(columns=_UNIT_COLUMNS_IAAS, id="status-units-table", cursor=False)
            yield Label("Machines", classes="section-label", id="status-machines-label")
            yield ResourceTable(
                columns=_MACHINE_COLUMNS, id="status-machines-table", cursor=False
            )
            yield Label("Offers", classes="section-label", id="status-offers-label")
            yield ResourceTable(columns=_OFFER_COLUMNS, id="status-offers-table", cursor=False)
            yield Label("Relations", classes="section-label")
            yield ResourceTable(columns=_REL_COLUMNS, id="status-rels-table", cursor=False)
        yield Label("▼ more below", id="scroll-indicator")

    def on_mount(self) -> None:
        self.query_one("#status-offers-label").display = False
        self.query_one("#status-offers-table").display = False
        self.query_one("#status-machines-label").display = False
        self.query_one("#status-machines-table").display = False
        self._update_scroll_indicator()

    def _update_scroll_indicator(self) -> None:
        try:
            vs = self.query_one(_TrackedScroll)
        except Exception:
            return
        at_bottom = vs.scroll_y >= vs.max_scroll_y
        self._show_more = not at_bottom and vs.max_scroll_y > 0

    def on_resize(self) -> None:
        self._update_scroll_indicator()

    def _watch__show_more(self, value: bool) -> None:
        try:
            self.query_one("#scroll-indicator").display = value
        except Exception:
            pass

    def update_apps(self, apps: list[AppInfo]) -> None:
        rows = []
        heights = []
        for a in apps:
            msg, h = _wrap_msg(a.message)
            rows.append((
                a.name,
                a.version,
                _colored_status(a.status),
                str(a.unit_count),
                a.charm,
                a.channel,
                str(a.revision),
                _colored_ip(a.address),
                "yes" if a.exposed else "no",
                msg,
            ))
            heights.append(h)
        self.query_one("#status-apps-table", ResourceTable).update_rows(rows, heights=heights)
        logger.debug("StatusView apps updated: %d rows", len(rows))

    def update_units(self, units: list[UnitInfo], is_kubernetes: bool = False) -> None:
        table = self.query_one("#status-units-table", ResourceTable)
        ordered = _group_units(units)
        rows = []
        heights = []
        if is_kubernetes:
            table.reset_columns(_UNIT_COLUMNS_K8S)
            for u in ordered:
                name = f"  {u.name}" if u.subordinate_of else u.name
                msg, h = _wrap_msg(u.message)
                rows.append((
                    name,
                    _colored_status(u.workload_status),
                    _colored_status(u.agent_status),
                    _colored_ip(u.address), u.ports, msg,
                ))
                heights.append(h)
        else:
            table.reset_columns(_UNIT_COLUMNS_IAAS)
            for u in ordered:
                name = f"  {u.name}" if u.subordinate_of else u.name
                machine = "" if u.subordinate_of else u.machine
                msg, h = _wrap_msg(u.message)
                rows.append((
                    name,
                    _colored_status(u.workload_status),
                    _colored_status(u.agent_status),
                    machine, _colored_ip(u.public_address), u.ports, msg,
                ))
                heights.append(h)
        table.update_rows(rows, heights=heights)
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

    def update_machines(
        self, machines: list[MachineInfo], is_kubernetes: bool = False
    ) -> None:
        show = bool(machines) and not is_kubernetes
        self.query_one("#status-machines-label").display = show
        self.query_one("#status-machines-table").display = show
        if not show:
            self.query_one("#status-machines-table", ResourceTable).update_rows([])
            return
        rows = []
        heights = []
        for m in machines:
            msg, h = _wrap_msg(m.message)
            rows.append((
                m.id, _colored_status(m.state), _colored_ip(m.address), m.instance_id, m.base, m.az, msg,
            ))
            heights.append(h)
        self.query_one("#status-machines-table", ResourceTable).update_rows(
            rows, heights=heights
        )
        logger.debug("StatusView machines updated: %d rows", len(rows))

    def update_relations(self, relations: list[RelationInfo]) -> None:
        rows = [
            (_colored_relation(r.provider), _colored_relation(r.requirer), r.interface, r.type)
            for r in relations
        ]
        self.query_one("#status-rels-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView relations updated: %d rows", len(rows))
