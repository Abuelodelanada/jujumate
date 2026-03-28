"""Cross-model health view — split pane showing all models and their issues.

Left panel : all models across all controllers, sorted by worst status
             (error → blocked → maintenance → waiting → active).
Right panel: all units of the selected model, sorted by severity, with
             their workload status and message.
"""

from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Label

from jujumate import palette
from jujumate.models.entities import AppInfo, ModelInfo, UnitInfo

# ── Status helpers ────────────────────────────────────────────────────────────

_STATUS_RANK: dict[str, int] = {
    "error": 0,
    "blocked": 1,
    "maintenance": 2,
    "waiting": 3,
    "executing": 3,
    "active": 4,
    "idle": 4,
    "started": 4,
}

_STATUS_SYMBOL: dict[str, str] = {
    "error": "✗",
    "blocked": "✗",
    "maintenance": "⚠",
    "waiting": "⚠",
    "executing": "⚠",
    "active": "●",
    "idle": "●",
    "started": "●",
}

_HEALTHY = frozenset({"active", "idle", "started"})


def _rank(status: str) -> int:
    return _STATUS_RANK.get(status.strip().lower(), 3)


def _status_color(status: str) -> str:
    s = status.strip().lower()
    if s == "error":
        return palette.ERROR
    if s == "blocked":
        return palette.BLOCKED
    if s in ("maintenance", "waiting", "executing"):
        return palette.WARNING
    if s in _HEALTHY:
        return palette.SUCCESS
    return palette.MUTED


def _colored_dot(status: str) -> Text:
    """Return a colored status symbol."""
    s = status.strip().lower()
    symbol = _STATUS_SYMBOL.get(s, "●")
    color = _status_color(s)
    return Text.from_markup(f"[{color}]{symbol}[/]") if color else Text(symbol)


def _colored_status(status: str) -> Text:
    """Return a colored status label (symbol + text)."""
    s = status.strip().lower()
    symbol = _STATUS_SYMBOL.get(s, "●")
    color = _status_color(s)
    label = f"{symbol} {status}" if status else "●"
    return Text.from_markup(f"[{color}]{label}[/]") if color else Text(label)


def _model_worst_status(apps: list[AppInfo]) -> str:
    """Return the worst app status for a model (lowest rank = worst)."""
    if not apps:
        return "active"
    return min((a.status.strip().lower() for a in apps), key=_rank, default="active")


# ── Widget ────────────────────────────────────────────────────────────────────


class HealthView(Widget):
    """Split-pane health overview: models list (left) + unit issues (right)."""

    DEFAULT_CSS = (Path(__file__).parent / "health_view.tcss").read_text()

    _show_all: reactive[bool] = reactive(False)

    class ModelDrillDown(Message):
        """Posted when the user presses Enter on a model row to drill into Status."""

        def __init__(self, controller: str, model: str) -> None:
            super().__init__()
            self.controller = controller
            self.model = model

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._all_models: list[ModelInfo] = []
        self._all_apps: list[AppInfo] = []
        self._all_units: list[UnitInfo] = []
        # (controller, model_name) of the currently focused row in the left panel
        self._selected: tuple[str, str] | None = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="health-left-panel"):
                yield DataTable(
                    id="health-models-table",
                    cursor_type="row",
                    show_cursor=True,
                    cursor_foreground_priority="renderable",
                )
                yield Label("", id="health-summary")
            with Vertical(id="health-right-panel"):
                yield DataTable(
                    id="health-issues-table",
                    cursor_type="row",
                    show_cursor=False,
                    cursor_foreground_priority="renderable",
                )

    def on_mount(self) -> None:
        left_panel = self.query_one("#health-left-panel", Vertical)
        left_panel.border_title = "Models"

        right_panel = self.query_one("#health-right-panel", Vertical)
        right_panel.border_title = "Select a model"

        models_dt = self.query_one("#health-models-table", DataTable)
        models_dt.add_column("", width=3, key="dot")
        models_dt.add_column("Ctrl", key="controller")
        models_dt.add_column("Model", key="model")
        models_dt.add_column("Issues", width=6, key="issues")

        issues_dt = self.query_one("#health-issues-table", DataTable)
        issues_dt.add_column("App", width=20, key="app")
        issues_dt.add_column("Unit", width=16, key="unit")
        issues_dt.add_column("Status", width=16, key="status")
        issues_dt.add_column("Message", key="message")

    # ── Public API ────────────────────────────────────────────────────────────

    def update(
        self,
        models: list[ModelInfo],
        apps: list[AppInfo],
        units: list[UnitInfo],
    ) -> None:
        """Refresh both panels with new data from the poller."""
        self._all_models = models
        self._all_apps = apps
        self._all_units = units
        self._render_models()
        if self._selected:
            self._render_issues(*self._selected)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _apps_by_model(self) -> dict[tuple[str, str], list[AppInfo]]:
        result: dict[tuple[str, str], list[AppInfo]] = {}
        for app in self._all_apps:
            result.setdefault((app.controller, app.model), []).append(app)
        return result

    def _units_by_model(self) -> dict[tuple[str, str], list[UnitInfo]]:
        result: dict[tuple[str, str], list[UnitInfo]] = {}
        for unit in self._all_units:
            result.setdefault((unit.controller, unit.model), []).append(unit)
        return result

    def _render_models(self) -> None:
        models_dt = self.query_one("#health-models-table", DataTable)
        summary_label = self.query_one("#health-summary", Label)
        apps_by_model = self._apps_by_model()
        units_by_model = self._units_by_model()

        def _sort_key(m: ModelInfo) -> tuple[int, str, str]:
            worst = _model_worst_status(apps_by_model.get((m.controller, m.name), []))
            return (_rank(worst), m.controller, m.name)

        sorted_models = sorted(self._all_models, key=_sort_key)

        def _is_unhealthy(m: ModelInfo) -> bool:
            apps = apps_by_model.get((m.controller, m.name), [])
            units = units_by_model.get((m.controller, m.name), [])
            worst_app = _model_worst_status(apps)
            worst_unit = min(
                (u.workload_status.strip().lower() for u in units), key=_rank, default="active"
            )
            return worst_app not in _HEALTHY or worst_unit not in _HEALTHY

        displayed_models = (
            sorted_models if self._show_all else [m for m in sorted_models if _is_unhealthy(m)]
        )

        # Resolve which row was previously selected
        selected_row: int | None = None
        first_unhealthy: int | None = None
        total_issues = 0

        models_dt.clear()
        for i, m in enumerate(displayed_models):
            apps = apps_by_model.get((m.controller, m.name), [])
            worst = _model_worst_status(apps)
            dot = _colored_dot(worst)

            issue_count = sum(1 for a in apps if a.status.strip().lower() not in _HEALTHY)
            total_issues += issue_count
            if issue_count:
                issues_cell = Text.from_markup(f"[{palette.ERROR}]{issue_count}[/]")
                if first_unhealthy is None:
                    first_unhealthy = i
            else:
                issues_cell = Text.from_markup(f"[{palette.SUCCESS}]✓[/]")

            row_key = f"{m.controller}/{m.name}"
            models_dt.add_row(dot, m.controller, m.name, issues_cell, key=row_key)

            if self._selected == (m.controller, m.name):
                selected_row = i

        # Update summary footer
        total = len(sorted_models)
        shown = len(displayed_models)
        filter_indicator = (
            f"[{palette.MUTED}] · f: show all[/]"
            if not self._show_all
            else f"[{palette.WARNING}] · f: unhealthy only[/]"
        )
        if total_issues:
            summary_label.update(
                Text.from_markup(
                    f" {shown}/{total} models  [{palette.ERROR}]{total_issues} issues[/]"
                    f"{filter_indicator}"
                )
            )
        else:
            summary_label.update(
                Text.from_markup(
                    f" {shown}/{total} models  [{palette.SUCCESS}]✓ all healthy[/]"
                    f"{filter_indicator}"
                )
            )

        if not displayed_models:
            return

        # Auto-select: restore previous, or pick first unhealthy, or first row
        if selected_row is not None:
            models_dt.move_cursor(row=selected_row)
        else:
            target = first_unhealthy if first_unhealthy is not None else 0
            m = displayed_models[target]
            self._selected = (m.controller, m.name)
            models_dt.move_cursor(row=target)
            self._render_issues(m.controller, m.name)

    def _render_issues(self, controller: str, model: str) -> None:
        issues_dt = self.query_one("#health-issues-table", DataTable)
        right_panel = self.query_one("#health-right-panel", Vertical)

        units = [u for u in self._all_units if u.controller == controller and u.model == model]
        apps = [a for a in self._all_apps if a.controller == controller and a.model == model]

        issue_count = sum(1 for u in units if u.workload_status.strip().lower() not in _HEALTHY)

        if issue_count:
            right_panel.border_title = f"{model} — ✗ {issue_count} issue(s)"
        else:
            right_panel.border_title = f"{model} — ● all healthy"

        issues_dt.clear()

        if units:
            sorted_units = sorted(units, key=lambda u: (_rank(u.workload_status), u.app, u.name))
            for u in sorted_units:
                msg = u.message
                if len(msg) > 64:
                    msg = msg[:63] + "…"
                issues_dt.add_row(
                    u.app,
                    u.name,
                    _colored_status(u.workload_status),
                    msg,
                )
        elif apps:
            # Model has apps but no units yet (e.g. pending K8s deploy)
            sorted_apps = sorted(apps, key=lambda a: (_rank(a.status), a.name))
            for a in sorted_apps:
                msg = a.message
                if len(msg) > 64:
                    msg = msg[:63] + "…"
                issues_dt.add_row(
                    a.name,
                    "–",
                    _colored_status(a.status),
                    msg,
                )

    # ── Filter toggle ─────────────────────────────────────────────────────────

    def action_toggle_filter(self) -> None:
        self._show_all = not self._show_all
        self._render_models()

    # ── Events ────────────────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update the right panel when the cursor moves in the models table."""
        if event.data_table.id != "health-models-table":
            return
        if not event.row_key or event.row_key.value is None:
            return
        key = str(event.row_key.value)
        parts = key.split("/", 1)
        if len(parts) == 2:
            self._selected = (parts[0], parts[1])
            self._render_issues(parts[0], parts[1])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Drill into Status tab when the user presses Enter on a model row."""
        if event.data_table.id != "health-models-table":
            return
        if not event.row_key or event.row_key.value is None:
            return
        key = str(event.row_key.value)
        parts = key.split("/", 1)
        if len(parts) == 2:
            self.post_message(self.ModelDrillDown(controller=parts[0], model=parts[1]))
