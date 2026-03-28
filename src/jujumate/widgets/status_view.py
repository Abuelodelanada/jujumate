from pathlib import Path
from typing import Any

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label

from jujumate import palette
from jujumate.models.entities import (
    AppInfo,
    MachineInfo,
    OfferInfo,
    RelationInfo,
    SAASInfo,
    UnitInfo,
)
from jujumate.widgets.resource_table import Column, ResourceTable


def _status_color(status: str) -> str:
    return {
        "active": palette.SUCCESS,
        "idle": palette.SUCCESS,
        "started": palette.SUCCESS,
        "blocked": palette.BLOCKED,
        "error": palette.ERROR,
        "terminated": palette.ERROR,
        "maintenance": palette.WARNING,
        "waiting": palette.WARNING,
        "executing": palette.WARNING,
        "unknown": palette.MUTED,
    }.get(status, "")


def _colored_status(status: str) -> Text:
    """Return a Rich Text object with the status colored by severity."""
    color = _status_color(status.strip().lower())
    if color:
        return Text.from_markup(f"[{color}]{status}[/]")
    return Text(status)


def _colored_ip(address: str) -> Text:
    """Color an IP address."""
    if address:
        return Text(address, style=palette.LINK)
    return Text(address)


def _colored_relation(endpoint: str) -> Text:
    """Color the :rel_name part of an APP:REL endpoint."""
    if ":" in endpoint:
        app, rel = endpoint.split(":", 1)
        text = Text(app)
        text.append(":", style=palette.LINK)
        text.append(rel, style=palette.LINK)
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
    Column("Interface", "s-rel-iface"),
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


def _highlight(text: str, needle: str) -> Text:
    """Return Rich Text with every case-insensitive occurrence of needle highlighted."""
    if not needle or needle.lower() not in text.lower():
        return Text(text)
    result = Text()
    lower_text = text.lower()
    lower_needle = needle.lower()
    needle_len = len(needle)
    start = 0
    while True:
        idx = lower_text.find(lower_needle, start)
        if idx == -1:
            result.append(text[start:])
            break
        result.append(text[start:idx])
        result.append(text[idx : idx + needle_len], style=f"bold {palette.ACCENT}")
        start = idx + needle_len
    return result


def _matches_filter(text: str, *fields: Any) -> bool:
    """Return True if *text* is a case-insensitive substring of any field, or text is empty."""
    if not text:
        return True
    lf = text.lower()
    return any(lf in str(f).lower() for f in fields)


def _trunc_msg(text: str) -> str:
    """Truncate a message to _MSG_TRUNC_WIDTH chars, appending … if needed."""
    if len(text) <= _MSG_TRUNC_WIDTH:
        return text
    return text[: _MSG_TRUNC_WIDTH - 1] + "…"


def _group_units(units: list) -> list[tuple]:
    """Return (unit, tree_prefix) tuples with subordinates placed after their principal.

    tree_prefix is "" for principals, "├─ " for non-last subordinates, "└─ " for the last.
    """
    principals = [u for u in units if not u.subordinate_of]
    known_principals = {p.name for p in principals}
    result: list[tuple] = []
    for principal in principals:
        result.append((principal, ""))
        subs = [u for u in units if u.subordinate_of == principal.name]
        for i, sub in enumerate(subs):
            prefix = "└─ " if i == len(subs) - 1 else "├─ "
            result.append((sub, prefix))
    # Orphan subordinates (principal not present in this view)
    for u in units:
        if u.subordinate_of and u.subordinate_of not in known_principals:
            result.append((u, "└─ "))
    return result


def _group_units_by_machine(
    machines: list[MachineInfo], units: list[UnitInfo]
) -> list[tuple[MachineInfo | UnitInfo, str]]:
    """Return (item, tree_prefix) tuples: each machine followed by its nested units.

    Structure per machine:
      Machine           → prefix ""
      ├─ principal/0   → "├─ "  (non-last principal)
      │  └─ sub/0      → "│  └─ " (last sub under non-last principal)
      └─ principal/1   → "└─ "  (last principal)
         └─ sub/1      → "   └─ " (last sub under last principal)
    """
    principals_by_machine: dict[str, list[UnitInfo]] = {}
    subs_by_principal: dict[str, list[UnitInfo]] = {}
    for u in units:
        if u.subordinate_of:
            subs_by_principal.setdefault(u.subordinate_of, []).append(u)
        elif u.machine:
            principals_by_machine.setdefault(u.machine, []).append(u)

    result: list[tuple[MachineInfo | UnitInfo, str]] = []
    for m in machines:
        result.append((m, ""))
        principals = sorted(principals_by_machine.get(m.id, []), key=lambda u: u.name)
        for pi, principal in enumerate(principals):
            is_last_principal = pi == len(principals) - 1
            p_prefix = "└─ " if is_last_principal else "├─ "
            result.append((principal, p_prefix))
            subs = sorted(subs_by_principal.get(principal.name, []), key=lambda u: u.name)
            continuation = "   " if is_last_principal else "│  "
            for si, sub in enumerate(subs):
                is_last_sub = si == len(subs) - 1
                s_prefix = continuation + ("└─ " if is_last_sub else "├─ ")
                result.append((sub, s_prefix))
    return result


class _TrackedScroll(VerticalScroll, can_focus=False):
    """VerticalScroll that notifies its parent when scroll_y changes."""

    def watch_scroll_y(self, value: float) -> None:  # type: ignore[override]
        if isinstance(self.parent, StatusView):
            self.parent._update_scroll_indicator()


class StatusView(Widget):
    """Displays a juju-status–style overview for the selected model."""

    BINDINGS = [
        Binding("/", "activate_filter", show=False),
        Binding("escape", "close_filter", show=False),
        Binding("y", "copy_to_clipboard", "Copy status", show=False),
        Binding("p", "toggle_peer_relations", "Toggle peer relations", show=False),
        Binding("u", "toggle_units_in_machines", "Toggle units in machines", show=False),
    ]

    class RelationSelected(Message):
        """Posted when the user presses Enter on a relation row."""

        def __init__(self, relation: RelationInfo) -> None:
            super().__init__()
            self.relation = relation

    class AppSelected(Message):
        """Posted when the user presses Enter on an app row."""

        def __init__(self, app: AppInfo) -> None:
            super().__init__()
            self.app = app

    class OfferSelected(Message):
        """Posted when the user presses Enter on an offer row."""

        def __init__(self, offer: OfferInfo) -> None:
            super().__init__()
            self.offer = offer

    DEFAULT_CSS = (Path(__file__).parent / "status_view.tcss").read_text()

    _show_more: reactive[bool] = reactive(False)
    _filter: reactive[str] = reactive("", init=False)
    _show_peer_relations: reactive[bool] = reactive(False)
    _show_units_in_machines: reactive[bool] = reactive(False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._row_messages: dict[str, list[str]] = {}
        self._last_cursor: dict[str, int] = {}
        self._last_active_table: str = ""
        self._relations: list[RelationInfo] = []
        self._apps: list[AppInfo] = []
        self._all_saas: list[SAASInfo] = []
        self._all_units: list[UnitInfo] = []
        self._all_machines: list[MachineInfo] = []
        self._all_offers: list[OfferInfo] = []
        self._all_relations: list[RelationInfo] = []
        self._displayed_apps: list[AppInfo] = []
        self._displayed_relations: list[RelationInfo] = []
        self._displayed_offers: list[OfferInfo] = []
        self._is_kubernetes: bool = False
        self._ctx_cloud: str = ""
        self._ctx_controller: str = ""
        self._ctx_model: str = ""
        self._ctx_juju_version: str = ""

    def compose(self) -> ComposeResult:
        with _TrackedScroll(id="status-scroll"):
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
            yield t
        with Horizontal(id="filter-bar"):
            yield Label("Filter: ")
            yield Input(placeholder="type to filter…", id="filter-input")
        yield Label("", id="msg-bar")
        yield Label("▼ more below", id="scroll-indicator")

    def on_mount(self) -> None:
        self.query_one("#status-saas-table").display = False
        self.query_one("#status-offers-table").display = False
        self.query_one("#status-machines-table").display = False
        self.query_one("#status-rels-table").display = False
        self._update_rels_border_title()
        self._update_machines_border_title()
        self._update_scroll_indicator()

    def update_context(self, cloud: str, controller: str, model: str, juju_version: str) -> None:
        """Store context metadata used in the clipboard header."""
        self._ctx_cloud = cloud
        self._ctx_controller = controller
        self._ctx_model = model
        self._ctx_juju_version = juju_version

    def _update_scroll_indicator(self) -> None:
        try:
            vs = self.query_one("#status-scroll", _TrackedScroll)
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
        self._apps = apps
        self._render_apps()

    def _render_apps(self) -> None:
        filtered = [
            a
            for a in self._apps
            if _matches_filter(self._filter, a.name, a.charm, a.channel, a.status, a.message)
        ]
        self._displayed_apps = filtered
        rows = []
        full_msgs = []
        for a in filtered:
            rows.append(
                (
                    _highlight(a.name, self._filter),
                    _highlight(a.version, self._filter),
                    _colored_status(a.status),
                    str(a.unit_count),
                    _highlight(a.charm, self._filter),
                    _highlight(a.channel, self._filter),
                    Text(str(a.revision), style=f"bold {palette.WARNING}")
                    if a.can_upgrade_to
                    else str(a.revision),
                    _colored_ip(a.address),
                    "yes" if a.exposed else "no",
                    _highlight(_trunc_msg(a.message), self._filter),
                )
            )
            full_msgs.append(a.message)
        self._row_messages["status-apps-table"] = full_msgs
        self.query_one("#status-apps-table", ResourceTable).update_rows(rows)
        self._restore_cursor("status-apps-table", len(full_msgs))

    def update_saas(self, saas: list[SAASInfo]) -> None:
        self._all_saas = saas
        self._render_saas()

    def _render_saas(self) -> None:
        filtered = [
            s
            for s in self._all_saas
            if _matches_filter(self._filter, s.name, s.status, s.store, s.url)
        ]
        rows = [
            (
                _highlight(s.name, self._filter),
                _colored_status(s.status),
                _highlight(s.store, self._filter),
                _highlight(s.url, self._filter),
            )
            for s in filtered
        ]
        has_saas = bool(rows)
        self.query_one("#status-saas-table").display = has_saas
        self.query_one("#status-saas-table", ResourceTable).update_rows(rows)

    def update_units(self, units: list[UnitInfo], is_kubernetes: bool = False) -> None:
        self._all_units = units
        self._is_kubernetes = is_kubernetes
        self._render_units()

    def _render_units(self) -> None:
        table = self.query_one("#status-units-table", ResourceTable)
        filtered = [
            u
            for u in self._all_units
            if _matches_filter(
                self._filter,
                u.name,
                u.workload_status,
                u.agent_status,
                u.machine,
                u.public_address,
                u.address,
                u.message,
            )
        ]
        ordered = _group_units(filtered)
        rows = []
        full_msgs = []
        if self._is_kubernetes:
            table.reset_columns(_UNIT_COLUMNS_K8S)
            for u, tree_prefix in ordered:
                if tree_prefix:
                    name = Text()
                    name.append(tree_prefix, style=palette.MUTED)
                    name.append_text(_highlight(u.name, self._filter))
                else:
                    name = _highlight(u.name, self._filter)
                rows.append(
                    (
                        name,
                        _colored_status(u.workload_status),
                        _colored_status(u.agent_status),
                        _colored_ip(u.address),
                        _highlight(u.ports, self._filter),
                        _highlight(_trunc_msg(u.message), self._filter),
                    )
                )
                full_msgs.append(u.message)
        else:
            table.reset_columns(_UNIT_COLUMNS_IAAS)
            for u, tree_prefix in ordered:
                if tree_prefix:
                    name = Text()
                    name.append(tree_prefix, style=palette.MUTED)
                    name.append_text(_highlight(u.name, self._filter))
                else:
                    name = _highlight(u.name, self._filter)
                machine = "" if u.subordinate_of else u.machine
                rows.append(
                    (
                        name,
                        _colored_status(u.workload_status),
                        _colored_status(u.agent_status),
                        _highlight(machine, self._filter),
                        _colored_ip(u.public_address),
                        _highlight(u.ports, self._filter),
                        _highlight(_trunc_msg(u.message), self._filter),
                    )
                )
                full_msgs.append(u.message)
        self._row_messages["status-units-table"] = full_msgs
        table.update_rows(rows)
        self._restore_cursor("status-units-table", len(full_msgs))

    def update_offers(self, offers: list[OfferInfo]) -> None:
        self._all_offers = offers
        self._render_offers()

    def _render_offers(self) -> None:
        filtered = [
            o
            for o in self._all_offers
            if _matches_filter(
                self._filter, o.name, o.application, o.charm, o.endpoint, o.interface
            )
        ]
        has_offers = bool(filtered)
        self._displayed_offers = filtered
        self.query_one("#status-offers-table").display = has_offers
        rows = [
            (
                _highlight(o.name, self._filter),
                _highlight(o.application, self._filter),
                _highlight(o.charm, self._filter),
                str(o.rev),
                o.connected,
                _highlight(o.endpoint, self._filter),
                _highlight(o.interface, self._filter),
                o.role,
            )
            for o in filtered
        ]
        self.query_one("#status-offers-table", ResourceTable).update_rows(rows)
        self._restore_cursor("status-offers-table", len(rows))

    def update_machines(self, machines: list[MachineInfo], is_kubernetes: bool = False) -> None:
        self._all_machines = machines
        self._is_kubernetes = is_kubernetes
        self._render_machines()

    def _render_machines(self) -> None:
        show = bool(self._all_machines) and not self._is_kubernetes
        self.query_one("#status-machines-table").display = show
        if not show:
            self.query_one("#status-machines-table", ResourceTable).update_rows([])
            return
        filtered = [
            m
            for m in self._all_machines
            if _matches_filter(
                self._filter, m.id, m.state, m.address, m.instance_id, m.base, m.az, m.message
            )
        ]
        rows = []
        full_msgs = []
        if self._show_units_in_machines:
            items = _group_units_by_machine(filtered, self._all_units)
            for item, prefix in items:
                if isinstance(item, MachineInfo):
                    rows.append(
                        (
                            _highlight(item.id, self._filter),
                            _colored_status(item.state),
                            _colored_ip(item.address),
                            _highlight(item.instance_id, self._filter),
                            _highlight(item.base, self._filter),
                            _highlight(item.az, self._filter),
                            _highlight(_trunc_msg(item.message), self._filter),
                        )
                    )
                    full_msgs.append(item.message)
                else:
                    name = Text()
                    name.append(prefix, style=palette.MUTED)
                    name.append_text(_highlight(item.name, self._filter))
                    rows.append(
                        (
                            name,
                            _colored_status(item.workload_status),
                            _colored_ip(item.public_address or item.address),
                            Text(""),
                            Text(""),
                            Text(""),
                            _highlight(_trunc_msg(item.message), self._filter),
                        )
                    )
                    full_msgs.append(item.message)
        else:
            for m in filtered:
                rows.append(
                    (
                        _highlight(m.id, self._filter),
                        _colored_status(m.state),
                        _colored_ip(m.address),
                        _highlight(m.instance_id, self._filter),
                        _highlight(m.base, self._filter),
                        _highlight(m.az, self._filter),
                        _highlight(_trunc_msg(m.message), self._filter),
                    )
                )
                full_msgs.append(m.message)
        self._row_messages["status-machines-table"] = full_msgs
        self.query_one("#status-machines-table", ResourceTable).update_rows(rows)
        self._restore_cursor("status-machines-table", len(full_msgs))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        try:
            table_id = event.data_table.parent.id or "" if event.data_table.parent else ""
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
        self._all_relations = relations
        self._render_relations()

    def _render_relations(self) -> None:
        filtered = sorted(
            (
                r
                for r in self._all_relations
                if (self._show_peer_relations or r.type != "peer")
                and _matches_filter(self._filter, r.provider, r.requirer, r.interface, r.type)
            ),
            key=lambda r: (r.type, r.provider, r.requirer),
        )
        self._displayed_relations = filtered
        self._relations = filtered
        rows = [
            (
                _colored_relation(r.provider),
                _colored_relation(r.requirer),
                _highlight(r.interface, self._filter),
                _highlight(r.type, self._filter),
            )
            for r in filtered
        ]
        table = self.query_one("#status-rels-table", ResourceTable)
        table.display = bool(rows)
        table.update_rows(rows)
        self._restore_cursor("status-rels-table", len(rows))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Post RelationSelected or AppSelected when user presses Enter on a row."""
        try:
            table_widget = event.data_table.parent
            table_id = getattr(table_widget, "id", None)
            idx = event.cursor_row
            if table_id == "status-rels-table":
                if 0 <= idx < len(self._displayed_relations):
                    self.post_message(StatusView.RelationSelected(self._displayed_relations[idx]))
            elif table_id == "status-apps-table":
                if 0 <= idx < len(self._displayed_apps):
                    self.post_message(StatusView.AppSelected(self._displayed_apps[idx]))
            elif table_id == "status-offers-table":
                if 0 <= idx < len(self._displayed_offers):
                    self.post_message(StatusView.OfferSelected(self._displayed_offers[idx]))
        except Exception:
            pass

    def _rerender_all(self) -> None:
        """Re-apply the current filter to all tables."""
        try:
            self._render_apps()
        except Exception:
            pass
        try:
            self._render_saas()
        except Exception:
            pass
        try:
            self._render_units()
        except Exception:
            pass
        try:
            self._render_offers()
        except Exception:
            pass
        try:
            self._render_machines()
        except Exception:
            pass
        try:
            self._render_relations()
        except Exception:
            pass

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "close_filter":
            try:
                bar = self.query_one("#filter-bar")
                return "visible" in bar.classes or bool(self._filter)
            except Exception:
                return False
        return True

    def action_activate_filter(self) -> None:
        bar = self.query_one("#filter-bar")
        fi = self.query_one("#filter-input", Input)
        bar.add_class("visible")
        fi.focus()

    def action_close_filter(self) -> None:
        fi = self.query_one("#filter-input", Input)
        fi.value = ""
        self._filter = ""
        self.query_one("#filter-bar").remove_class("visible")
        self._rerender_all()

    def _update_rels_border_title(self) -> None:
        table = self.query_one("#status-rels-table", ResourceTable)
        if self._show_peer_relations:
            table.border_title = f"Integrations  [{palette.SUCCESS}]peers: On[/]"
        else:
            table.border_title = f"Integrations  [{palette.ERROR}]peers: Off[/]"

    def action_toggle_peer_relations(self) -> None:
        self._show_peer_relations = not self._show_peer_relations
        self._update_rels_border_title()
        self._render_relations()

    def _update_machines_border_title(self) -> None:
        table = self.query_one("#status-machines-table", ResourceTable)
        if self._show_units_in_machines:
            table.border_title = f"Machines  [{palette.SUCCESS}]units: On[/]"
        else:
            table.border_title = f"Machines  [{palette.ERROR}]units: Off[/]"

    def action_toggle_units_in_machines(self) -> None:
        self._show_units_in_machines = not self._show_units_in_machines
        self._update_machines_border_title()
        self._render_machines()

    @on(Input.Changed, "#filter-input")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._filter = event.value
        self._rerender_all()

    def _format_for_clipboard(self) -> str:
        """Format all visible status data as plain text."""
        lines: list[str] = []

        # Header
        if any([self._ctx_cloud, self._ctx_controller, self._ctx_model, self._ctx_juju_version]):
            lines.append("Model:       " + (self._ctx_model or "—"))
            lines.append("Controller:  " + (self._ctx_controller or "—"))
            lines.append("Cloud:       " + (self._ctx_cloud or "—"))
            lines.append("Juju:        " + (self._ctx_juju_version or "—"))
            lines.append("")

        def section(title: str, headers: list[str], rows: list[list[str]]) -> None:
            widths = [len(h) for h in headers]
            for row in rows:
                for i, cell in enumerate(row):
                    if i < len(widths):
                        widths[i] = max(widths[i], len(cell))
            fmt = "  ".join(f"{{:<{w}}}" for w in widths)
            lines.append(f"\n{title}")
            lines.append(fmt.format(*headers))
            lines.append("  ".join("─" * w for w in widths))
            for row in rows:
                padded = list(row) + [""] * (len(headers) - len(row))
                lines.append(fmt.format(*padded))

        if self._all_saas:
            section(
                "SAAS",
                ["SAAS", "Status", "Store", "URL"],
                [[s.name, s.status, s.store, s.url] for s in self._all_saas],
            )

        if self._displayed_apps:
            section(
                "Applications",
                [
                    "App",
                    "Version",
                    "Status",
                    "Scale",
                    "Charm",
                    "Channel",
                    "Rev",
                    "Address",
                    "Exposed",
                    "Message",
                ],
                [
                    [
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
                    ]
                    for a in self._displayed_apps
                ],
            )

        if self._all_units:
            if self._is_kubernetes:
                section(
                    "Units",
                    ["Unit", "Workload", "Agent", "Address", "Ports", "Message"],
                    [
                        [u.name, u.workload_status, u.agent_status, u.address, u.ports, u.message]
                        for u in self._all_units
                    ],
                )
            else:
                section(
                    "Units",
                    ["Unit", "Workload", "Agent", "Machine", "Public Address", "Ports", "Message"],
                    [
                        [
                            u.name,
                            u.workload_status,
                            u.agent_status,
                            "" if u.subordinate_of else u.machine,
                            u.public_address,
                            u.ports,
                            u.message,
                        ]
                        for u in self._all_units
                    ],
                )

        if self._all_machines and not self._is_kubernetes:
            section(
                "Machines",
                ["Machine", "State", "Address", "Inst id", "Base", "AZ", "Message"],
                [
                    [m.id, m.state, m.address, m.instance_id, m.base, m.az, m.message]
                    for m in self._all_machines
                ],
            )

        if self._displayed_offers:
            section(
                "Offers",
                [
                    "Offer",
                    "Application",
                    "Charm",
                    "Rev",
                    "Connected",
                    "Endpoint",
                    "Interface",
                    "Role",
                ],
                [
                    [
                        o.name,
                        o.application,
                        o.charm,
                        str(o.rev),
                        o.connected,
                        o.endpoint,
                        o.interface,
                        o.role,
                    ]
                    for o in self._displayed_offers
                ],
            )

        if self._displayed_relations:
            section(
                "Integrations",
                ["Provider", "Requirer", "Interface", "Type"],
                [[r.provider, r.requirer, r.interface, r.type] for r in self._displayed_relations],
            )

        return "\n".join(lines).strip()

    def action_copy_to_clipboard(self) -> None:
        text = self._format_for_clipboard()
        if not text:
            self.notify("Nothing to copy", severity="warning")
            return
        self.app.copy_to_clipboard(text)
        self.notify("Status copied to clipboard")

    @on(Input.Submitted, "#filter-input")
    def _on_filter_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#filter-bar").remove_class("visible")
