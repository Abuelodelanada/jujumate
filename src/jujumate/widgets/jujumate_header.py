import logging
from dataclasses import dataclass
from typing import Any

from textual.widgets import Static

logger = logging.getLogger(__name__)

_LOGO = "⬡ JujuMate"
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


class JujuMateHeader(Static):
    """Two-line contextual header: identity + drill-down breadcrumb + live stats."""

    DEFAULT_CSS = """
    JujuMateHeader {
        height: 4;
        dock: top;
        background: transparent;
        padding: 1 2;
        color: $primary;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("", *args, **kwargs)
        self._header_ctx = HeaderContext()

    def update_context(self, ctx: HeaderContext) -> None:
        self._header_ctx = ctx
        breadcrumb = self._build_breadcrumb(ctx)
        status = self._build_status(ctx)
        stats = self._build_stats(ctx)
        line1 = f"[bold]{_LOGO}[/bold]"
        if breadcrumb:
            line1 += f"   {breadcrumb}"
        if status:
            line1 += f"   {status}"
        line2 = f"[dim]{_SUBTITLE}[/dim]"
        if stats:
            line2 += f"   {stats}"
        self.update(f"{line1}\n{line2}")

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
