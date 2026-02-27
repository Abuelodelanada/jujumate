import logging
from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

logger = logging.getLogger(__name__)

_APP_NAME = "⬡ JujuMate"
_SUBTITLE = "Juju infrastructure TUI"


@dataclass
class HeaderContext:
    active_tab: str = ""
    selected_cloud: str | None = None
    selected_controller: str | None = None
    selected_model: str | None = None
    selected_app: str | None = None
    cloud_count: int = 0
    controller_count: int = 0
    model_count: int = 0
    app_count: int = 0
    unit_count: int = 0
    offer_count: int = 0
    relation_count: int = 0
    is_connected: bool = False
    timestamp: str = ""


class JujuMateHeader(Widget):
    """Header with logo+identity on the left and contextual info on the right."""

    DEFAULT_CSS = """
    JujuMateHeader {
        height: 5;
        dock: top;
        background: ansi_default;
        layout: horizontal;
    }
    JujuMateHeader #header-left {
        width: auto;
        padding: 1 2;
        color: $primary;
    }
    JujuMateHeader #header-right {
        width: 1fr;
        padding: 1 2;
        color: $primary;
        text-align: right;
        content-align: right bottom;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._header_ctx = HeaderContext()

    def compose(self) -> ComposeResult:
        yield Static("", id="header-left")
        yield Static("", id="header-right")

    def update_context(self, ctx: HeaderContext) -> None:
        self._header_ctx = ctx
        status = self._build_status(ctx)
        breadcrumb = self._build_breadcrumb(ctx)
        stats = self._build_stats(ctx)

        left = f"[bold]{_APP_NAME}[/bold]\n{status}"
        self.query_one("#header-left", Static).update(left)

        right_lines = [f"[dim]{_SUBTITLE}[/dim]"]
        if breadcrumb:
            right_lines.append(breadcrumb)
        if stats:
            right_lines.append(stats)
        self.query_one("#header-right", Static).update("\n".join(right_lines))

    def _build_breadcrumb(self, ctx: HeaderContext) -> str:
        parts = []
        if ctx.selected_cloud:
            parts.append(f"cloud: {ctx.selected_cloud}")
        if ctx.selected_controller:
            parts.append(f"ctrl: {ctx.selected_controller}")
        if ctx.selected_model:
            parts.append(f"model: {ctx.selected_model}")
        if ctx.selected_app:
            parts.append(f"app: {ctx.selected_app}")
        return "  │  ".join(parts) if parts else ""

    def _build_stats(self, ctx: HeaderContext) -> str:
        tab = ctx.active_tab
        if tab == "tab-clouds":
            return f"clouds: {ctx.cloud_count}"
        elif tab == "tab-controllers":
            return f"controllers: {ctx.controller_count}"
        elif tab == "tab-models":
            return f"models: {ctx.model_count}"
        elif tab == "tab-status":
            parts = [f"apps: {ctx.app_count}", f"units: {ctx.unit_count}"]
            if ctx.offer_count:
                parts.append(f"offers: {ctx.offer_count}")
            if ctx.relation_count:
                parts.append(f"relations: {ctx.relation_count}")
            return "  ·  ".join(parts)
        elif tab == "tab-apps":
            return f"apps: {ctx.app_count}"
        elif tab == "tab-units":
            return f"units: {ctx.unit_count}"
        return ""

    def _build_status(self, ctx: HeaderContext) -> str:
        if ctx.is_connected and ctx.timestamp:
            return f"[green]⣾ Live · {ctx.timestamp}[/green]"
        if ctx.is_connected:
            return "[green]⣾ Live[/green]"
        return "[red]⚠ Disconnected[/red]"
