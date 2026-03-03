import logging
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Label

from jujumate.models.entities import AppInfo, MachineInfo, OfferInfo, RelationInfo, SAASInfo, UnitInfo
from jujumate.widgets.resource_table import Column, ResourceTable
logger = logging.getLogger(__name__)

_STATUS_COLORS: dict[str, str] = {
    "active": "#26A269",
    "idle": "#26A269",
    "started": "#26A269",
    "blocked": "#FF5555",
    "error": "#FF5555",
    "terminated": "#FF5555",
    "maintenance": "#EFB73E",
    "waiting": "#EFB73E",
    "executing": "#EFB73E",
    "unknown": "#888888",
}


def _colored_status(status: str) -> Text:
    """Return a Rich Text object with the status colored by severity."""
    color = _STATUS_COLORS.get(status.strip().lower(), "")
    if color:
        return Text.from_markup(f"[{color}]{status}[/]")
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

_SAAS_COLUMNS = [
    Column("SAAS", "s-saas-name"),
    Column("Status", "s-saas-status", width=12),
    Column("Store", "s-saas-store", width=18),
    Column("URL", "s-saas-url"),
]

_APP_COLUMNS = [
    Column("App", "s-app-name"),
    Column("Version", "s-app-version", width=10),
    Column("Status", "s-app-status", width=12),
    Column("Scale", "s-app-scale", width=6),
    Column("Charm", "s-app-charm"),
    Column("Channel", "s-app-channel"),
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
    Column("Application", "s-offer-app"),
    Column("Charm", "s-offer-charm"),
    Column("Rev", "s-offer-rev", width=5),
    Column("Connected", "s-offer-conn", width=10),
    Column("Endpoint", "s-offer-ep", width=20),
    Column("Interface", "s-offer-iface", width=22),
    Column("Role", "s-offer-role", width=10),
]

_REL_COLUMNS = [
    Column("Integration provider", "s-rel-provider"),
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


_MSG_TRUNC_WIDTH = 60


def _trunc_msg(text: str) -> str:
    """Truncate a message to _MSG_TRUNC_WIDTH chars, appending … if needed."""
    if len(text) <= _MSG_TRUNC_WIDTH:
        return text
    return text[: _MSG_TRUNC_WIDTH - 1] + "…"


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

    class RelationSelected(Message):
        """Posted when the user presses Enter on a relation row."""

        def __init__(self, relation: RelationInfo) -> None:
            super().__init__()
            self.relation = relation

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
        border: tall $accent;
        border-title-color: $accent;
        border-title-style: bold;
        margin-bottom: 1;
        padding: 0 1;
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
    StatusView #msg-bar {
        dock: bottom;
        height: 1;
        width: 100%;
        padding: 0 2;
        color: $text-muted;
        text-style: italic;
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
        self._row_messages: dict[str, list[str]] = {}
        self._last_cursor: dict[str, int] = {}
        self._last_active_table: str = ""
        self._relations: list[RelationInfo] = []

    def compose(self) -> ComposeResult:
        with _TrackedScroll():
            t = ResourceTable(columns=_SAAS_COLUMNS, id="status-saas-table")
            t.border_title = "SAAS"
            yield t
            t = ResourceTable(columns=_APP_COLUMNS, id="status-apps-table")
            t.border_title = "Applications"
            yield t
            t = ResourceTable(columns=_UNIT_COLUMNS_IAAS, id="status-units-table")
            t.border_title = "Units"
            yield t
            t = ResourceTable(columns=_MACHINE_COLUMNS, id="status-machines-table")
            t.border_title = "Machines"
            yield t
            t = ResourceTable(columns=_OFFER_COLUMNS, id="status-offers-table")
            t.border_title = "Offers"
            yield t
            t = ResourceTable(columns=_REL_COLUMNS, id="status-rels-table")
            t.border_title = "Relations"
            yield t
        yield Label("", id="msg-bar")
        yield Label("▼ more below", id="scroll-indicator")

    def on_mount(self) -> None:
        self.query_one("#status-saas-table").display = False
        self.query_one("#status-offers-table").display = False
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
        full_msgs = []
        for a in apps:
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
                _trunc_msg(a.message),
            ))
            full_msgs.append(a.message)
        self._row_messages["status-apps-table"] = full_msgs
        self.query_one("#status-apps-table", ResourceTable).update_rows(rows)
        self._restore_cursor("status-apps-table", len(full_msgs))
        logger.debug("StatusView apps updated: %d rows", len(rows))

    def update_saas(self, saas: list[SAASInfo]) -> None:
        rows = [(s.name, _colored_status(s.status), s.store, s.url) for s in saas]
        has_saas = bool(rows)
        self.query_one("#status-saas-table").display = has_saas
        self.query_one("#status-saas-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView SAAS updated: %d rows", len(rows))

    def update_units(self, units: list[UnitInfo], is_kubernetes: bool = False) -> None:
        table = self.query_one("#status-units-table", ResourceTable)
        ordered = _group_units(units)
        rows = []
        full_msgs = []
        if is_kubernetes:
            table.reset_columns(_UNIT_COLUMNS_K8S)
            for u in ordered:
                name = f"  {u.name}" if u.subordinate_of else u.name
                rows.append((
                    name,
                    _colored_status(u.workload_status),
                    _colored_status(u.agent_status),
                    _colored_ip(u.address), u.ports, _trunc_msg(u.message),
                ))
                full_msgs.append(u.message)
        else:
            table.reset_columns(_UNIT_COLUMNS_IAAS)
            for u in ordered:
                name = f"  {u.name}" if u.subordinate_of else u.name
                machine = "" if u.subordinate_of else u.machine
                rows.append((
                    name,
                    _colored_status(u.workload_status),
                    _colored_status(u.agent_status),
                    machine, _colored_ip(u.public_address), u.ports, _trunc_msg(u.message),
                ))
                full_msgs.append(u.message)
        self._row_messages["status-units-table"] = full_msgs
        table.update_rows(rows)
        self._restore_cursor("status-units-table", len(full_msgs))
        logger.debug("StatusView units updated: %d rows (k8s=%s)", len(rows), is_kubernetes)

    def update_offers(self, offers: list[OfferInfo]) -> None:
        has_offers = bool(offers)
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
        self.query_one("#status-machines-table").display = show
        if not show:
            self.query_one("#status-machines-table", ResourceTable).update_rows([])
            return
        rows = []
        full_msgs = []
        for m in machines:
            rows.append((
                m.id, _colored_status(m.state), _colored_ip(m.address), m.instance_id, m.base, m.az,
                _trunc_msg(m.message),
            ))
            full_msgs.append(m.message)
        self._row_messages["status-machines-table"] = full_msgs
        self.query_one("#status-machines-table", ResourceTable).update_rows(rows)
        self._restore_cursor("status-machines-table", len(full_msgs))
        logger.debug("StatusView machines updated: %d rows", len(rows))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            table_id = event.data_table.parent.id or ""
            self._last_cursor[table_id] = event.cursor_row
            # Only set the active table when the user is actually navigating it (has focus).
            # Programmatic events from refresh (clear + move_cursor) arrive without focus.
            if event.data_table.has_focus:
                self._last_active_table = table_id
            # Update msg-bar only for the active table to avoid refresh events from other
            # tables (e.g. machines "Running") overwriting the displayed message.
            if table_id != self._last_active_table:
                return
            msgs = self._row_messages.get(table_id, [])
            msg = msgs[event.cursor_row] if event.cursor_row < len(msgs) else ""
        except Exception:
            msg = ""
        try:
            self.query_one("#msg-bar", Label).update(msg)
        except Exception:
            pass

    def on_resource_table_table_focused(self, event: ResourceTable.TableFocused) -> None:
        """When a table gains focus via TAB, set it as active and refresh the msg-bar."""
        try:
            table_id = event.resource_table.id or ""
            if not table_id:
                return
            self._last_active_table = table_id
            dt = event.resource_table.query_one(DataTable)
            row = dt.cursor_row
            msgs = self._row_messages.get(table_id, [])
            msg = msgs[row] if row < len(msgs) else ""
            self.query_one("#msg-bar", Label).update(msg)
        except Exception:
            pass

    def _restore_cursor(self, table_id: str, row_count: int) -> None:
        """Restore cursor to last-known position after a data update.
        
        Enqueues a RowHighlighted(last_row) after clear()'s RowHighlighted(0),
        so Textual renders only the final (correct) state.
        """
        try:
            dt = self.query_one(f"#{table_id} DataTable", DataTable)
            last_row = self._last_cursor.get(table_id, 0)
            row = min(last_row, max(row_count - 1, 0))
            dt.move_cursor(row=row)
        except Exception:
            pass

    def update_relations(self, relations: list[RelationInfo]) -> None:
        self._relations = relations
        rows = [
            (_colored_relation(r.provider), _colored_relation(r.requirer), r.interface, r.type)
            for r in relations
        ]
        self.query_one("#status-rels-table", ResourceTable).update_rows(rows)
        logger.debug("StatusView relations updated: %d rows", len(rows))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Post RelationSelected when user presses Enter on a relation row."""
        try:
            table_widget = event.data_table.parent
            if not table_widget or getattr(table_widget, "id", None) != "status-rels-table":
                return
            idx = event.cursor_row
            if 0 <= idx < len(self._relations):
                self.post_message(StatusView.RelationSelected(self._relations[idx]))
        except Exception:
            pass
