import logging
from typing import Any

from rich import box as rich_box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Static

from jujumate.models.entities import RelationDataEntry, RelationInfo

logger = logging.getLogger(__name__)

# Ubuntu palette
_C_PROVIDER = "#77216F"   # Aubergine — provider side
_C_REQUIRER = "#E95420"   # Ubuntu Orange — requirer side
_C_PEER     = "#EFB73E"   # Yellow — peer side
_C_KEY      = "bold white"
_C_META     = "dim"


def _kv_table(data: dict[str, str]) -> Table:
    """Build a compact key→value Rich table for a single data bag."""
    t = Table(box=None, show_header=False, padding=(0, 1), expand=False)
    t.add_column("key", style=_C_KEY, no_wrap=True)
    t.add_column("value", overflow="fold")
    if data:
        for k, v in sorted(data.items()):
            t.add_row(k, v)
    else:
        t.add_row(Text("<empty>", style=_C_META), "")
    return t


def _unit_panel(unit_name: str, data: dict[str, str], is_leader: bool, color: str) -> Panel:
    """Render a single unit data bag as a titled panel."""
    title = Text()
    title.append(unit_name, style=f"bold {color}")
    if is_leader:
        title.append("*", style="bold yellow")
    return Panel(_kv_table(data), title=title, border_style=color, expand=True)


def _build_relation_renderable(
    relation: RelationInfo,
    entries: list[RelationDataEntry],
) -> Table:
    """Build the jhack-style two-column Rich table for relation data."""
    is_peer = relation.provider.split(":")[0] == relation.requirer.split(":")[0]
    provider_app = relation.provider.split(":")[0]
    requirer_app = relation.requirer.split(":")[0]
    provider_endpoint = relation.provider.split(":")[1] if ":" in relation.provider else ""
    requirer_endpoint = relation.requirer.split(":")[1] if ":" in relation.requirer else ""

    sides = ["peer"] if is_peer else ["provider", "requirer"]
    apps   = [provider_app] if is_peer else [provider_app, requirer_app]
    eps    = [provider_endpoint] if is_peer else [provider_endpoint, requirer_endpoint]
    colors = [_C_PEER] if is_peer else [_C_PROVIDER, _C_REQUIRER]

    # Group entries
    app_bags: dict[str, dict[str, str]] = {a: {} for a in apps}
    unit_bags: dict[str, dict[str, dict[str, str]]] = {a: {} for a in apps}

    for e in entries:
        app = e.unit  # for scope=app, unit field holds app name
        if e.scope == "app" and app in app_bags:
            app_bags[app][e.key] = e.value
        elif e.scope == "unit":
            # unit belongs to provider or requirer based on side
            side_idx = 0 if (e.side in ("provider", "peer")) else 1
            owner_app = apps[side_idx]
            unit_bags[owner_app].setdefault(e.unit, {})[e.key] = e.value

    # Outer table — one column per side
    outer = Table(
        box=rich_box.ROUNDED,
        show_header=True,
        expand=True,
        border_style="#E95420",
        header_style="bold",
    )
    for app, color in zip(apps, colors):
        outer.add_column(Text(app, style=f"bold {color}"), ratio=1)

    # ── Metadata row ────────────────────────────────────────────────────────
    meta_cells = []
    for side, ep, color in zip(sides, eps, colors):
        meta = Table(box=None, show_header=False, padding=(0, 1), expand=False)
        meta.add_column("k", style=_C_META, no_wrap=True)
        meta.add_column("v")
        meta.add_row("relation ID", str(relation.relation_id))
        meta.add_row("role", Text(side, style=f"bold {color}"))
        meta.add_row("endpoint", Text(ep, style=f"{color}"))
        meta.add_row("interface", relation.interface)
        meta_cells.append(meta)
    outer.add_row(*meta_cells)

    # ── Application data row ─────────────────────────────────────────────────
    app_cells = []
    for app, color in zip(apps, colors):
        label = Text("application data", style=f"bold {color}")
        bag_panel = Panel(
            _kv_table(app_bags[app]),
            border_style=color,
            expand=True,
        )
        app_cells.append(Group(label, bag_panel))
    outer.add_row(*app_cells)

    # ── Unit data row ────────────────────────────────────────────────────────
    unit_cells = []
    for app, color in zip(apps, colors):
        units = unit_bags[app]
        label = Text("unit data", style=f"bold {color}")
        if units:
            panels = [_unit_panel(u, d, False, color) for u, d in sorted(units.items())]
            unit_cells.append(Group(label, *panels))
        else:
            unit_cells.append(Group(label, Panel(Text("<empty>", style=_C_META), border_style=color)))
    outer.add_row(*unit_cells)

    return outer


def _format_plain_text(
    relation: RelationInfo,
    entries: list[RelationDataEntry],
) -> str:
    """Format relation data as plain text suitable for clipboard."""
    is_peer = relation.provider.split(":")[0] == relation.requirer.split(":")[0]
    provider_app = relation.provider.split(":")[0]
    requirer_app = relation.requirer.split(":")[0]
    provider_ep = relation.provider.split(":")[1] if ":" in relation.provider else ""
    requirer_ep = relation.requirer.split(":")[1] if ":" in relation.requirer else ""

    sides = ["peer"] if is_peer else ["provider", "requirer"]
    apps = [provider_app] if is_peer else [provider_app, requirer_app]
    eps = [provider_ep] if is_peer else [provider_ep, requirer_ep]

    # Group entries
    app_bags: dict[str, dict[str, str]] = {a: {} for a in apps}
    unit_bags: dict[str, dict[str, dict[str, str]]] = {a: {} for a in apps}

    for e in entries:
        if e.scope == "app" and e.unit in app_bags:
            app_bags[e.unit][e.key] = e.value
        elif e.scope == "unit":
            side_idx = 0 if (e.side in ("provider", "peer")) else 1
            owner_app = apps[side_idx]
            unit_bags[owner_app].setdefault(e.unit, {})[e.key] = e.value

    lines: list[str] = []
    lines.append(f"relation-id: {relation.relation_id}")
    lines.append(f"interface: {relation.interface}")
    lines.append(f"type: {relation.type}")
    lines.append("")

    for side, app, ep in zip(sides, apps, eps):
        lines.append(f"--- {app} ({side}) endpoint: {ep} ---")
        lines.append("  application data:")
        bag = app_bags.get(app, {})
        if bag:
            for k, v in sorted(bag.items()):
                lines.append(f"    {k}: {v}")
        else:
            lines.append("    <empty>")
        lines.append("  unit data:")
        units = unit_bags.get(app, {})
        if units:
            for unit_name, data in sorted(units.items()):
                lines.append(f"    {unit_name}:")
                for k, v in sorted(data.items()):
                    lines.append(f"      {k}: {v}")
        else:
            lines.append("    <empty>")
        lines.append("")

    return "\n".join(lines)


class RelationDataView(Widget):
    """Shows the data bags for a selected relation (jhack-style layout)."""

    BINDINGS = [
        Binding("y", "copy_to_clipboard", "Copy data", show=False),
    ]

    DEFAULT_CSS = """
    RelationDataView {
        height: 1fr;
    }
    RelationDataView #rd-scroll {
        height: 1fr;
        scrollbar-size-vertical: 0;
    }
    RelationDataView #rd-content {
        height: auto;
        padding: 0 1;
    }
    RelationDataView #rd-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_relation: RelationInfo | None = None
        self._current_entries: list[RelationDataEntry] = []

    def compose(self) -> ComposeResult:
        yield Label(
            "No relation selected — press Enter on a relation to see its data bags.",
            id="rd-empty",
        )
        with VerticalScroll(id="rd-scroll"):
            yield Static("", id="rd-content")

    def on_mount(self) -> None:
        self.query_one("#rd-scroll").display = False

    def update(self, relation: RelationInfo, entries: list[RelationDataEntry]) -> None:
        """Populate the view with relation data in jhack style."""
        self._current_relation = relation
        self._current_entries = entries
        renderable = _build_relation_renderable(relation, entries)
        self.query_one("#rd-content", Static).update(renderable)
        self.query_one("#rd-empty").display = False
        self.query_one("#rd-scroll").display = True
        logger.debug(
            "RelationDataView updated: relation %d, %d entries",
            relation.relation_id, len(entries),
        )

    def show_loading(self, relation: RelationInfo) -> None:
        """Show a loading state while data is being fetched."""
        provider_app = relation.provider.split(":")[0]
        requirer_app = relation.requirer.split(":")[0]
        self.query_one("#rd-empty").display = True
        self.query_one("#rd-empty", Label).update(
            f"Fetching data bags for {provider_app} ↔ {requirer_app}…"
        )
        self.query_one("#rd-scroll").display = False

    def show_error(self, relation: RelationInfo, error: str) -> None:
        """Show an error state when the fetch failed."""
        provider_app = relation.provider.split(":")[0]
        requirer_app = relation.requirer.split(":")[0]
        self.query_one("#rd-empty").display = True
        self.query_one("#rd-empty", Label).update(
            f"[red]Error fetching data bags for {provider_app} ↔ {requirer_app}:\n{error}[/red]"
        )
        self.query_one("#rd-scroll").display = False

    def action_copy_to_clipboard(self) -> None:
        if not self._current_relation or not self._current_entries:
            self.notify("No relation data to copy", severity="warning")
            return
        text = _format_plain_text(self._current_relation, self._current_entries)
        self.app.copy_to_clipboard(text)
        self.notify("Relation data copied to clipboard")

