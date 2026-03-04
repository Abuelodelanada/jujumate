import logging
from dataclasses import dataclass
from typing import Any

from rich.panel import Panel
from rich.text import Text as RichText
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from jujumate import palette

logger = logging.getLogger(__name__)

_SUBTITLE = "Juju infrastructure TUI"


@dataclass
class HeaderContext:
    active_tab: str = ""
    selected_cloud: str | None = None
    selected_controller: str | None = None
    selected_model: str | None = None
    cloud_count: int = 0
    controller_count: int = 0
    model_count: int = 0
    app_count: int = 0
    unit_count: int = 0
    offer_count: int = 0
    relation_count: int = 0
    saas_count: int = 0
    machine_count: int = 0
    is_connected: bool = False
    timestamp: str = ""


class JujuMateHeader(Widget):
    """Header with logo+identity on the left and contextual info on the right."""

    DEFAULT_CSS = """
    JujuMateHeader {
        height: 4;
        dock: top;
        background: ansi_default;
        layout: horizontal;
    }
    JujuMateHeader #header-left {
        width: auto;
        min-width: 30;
    }
    JujuMateHeader #header-right {
        width: 1fr;
        padding: 0 2;
        color: $primary;
        content-align: left middle;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._header_ctx = HeaderContext()
        self._pulse_on = True

    def on_mount(self) -> None:
        self.set_interval(0.8, self._tick_pulse)

    def _tick_pulse(self) -> None:
        self._pulse_on = not self._pulse_on
        self.update_context(self._header_ctx)

    def compose(self) -> ComposeResult:
        yield Static("", id="header-left")
        yield Static("", id="header-right")

    def update_context(self, ctx: HeaderContext) -> None:
        self._header_ctx = ctx
        status = self._build_status(ctx)
        breadcrumb = self._build_breadcrumb(ctx)
        stats = self._build_stats(ctx)

        # Left: bordered panel
        inner = RichText()
        inner.append(_SUBTITLE, style="dim")
        inner.append("\n")
        inner.append_text(RichText.from_markup(status))
        sec = palette.SECONDARY
        app_name = f"[bold {sec}]⬢[/bold {sec}] [bold white]JujuMate[/bold white]"
        left_panel = Panel(
            inner,
            title=app_name,
            border_style=palette.PRIMARY,
            padding=(0, 1),
        )
        self.query_one("#header-left", Static).update(left_panel)

        # Right: breadcrumb + separator + stats
        right_lines = []
        if breadcrumb:
            right_lines.append(breadcrumb)
            right_lines.append(f"[dim]{'─' * 60}[/dim]")
        if stats:
            right_lines.append(stats)
        self.query_one("#header-right", Static).update("\n".join(right_lines))

    def _build_breadcrumb(self, ctx: HeaderContext) -> str:
        parts = []
        p = palette.PRIMARY
        b, w = f"bold {p}", "bold white"
        if ctx.selected_cloud:
            parts.append(f"[{b}]cloud:[/{b}] [{w}]{ctx.selected_cloud}[/{w}]")
        if ctx.selected_controller:
            parts.append(f"[{b}]controller:[/{b}] [{w}]{ctx.selected_controller}[/{w}]")
        if ctx.selected_model:
            parts.append(f"[{b}]model:[/{b}] [{w}]{ctx.selected_model}[/{w}]")
        sep = " [dim]›[/dim] "
        return sep.join(parts) if parts else ""

    def _build_stats(self, ctx: HeaderContext) -> str:
        tab = ctx.active_tab
        p = palette.PRIMARY

        def stat(label: str, value: int) -> str:
            return f"[bold {p}]{label}:[/bold {p}] [bold white]{value}[/bold white]"

        if tab == "tab-clouds":
            return stat("clouds", ctx.cloud_count)
        elif tab == "tab-controllers":
            return stat("controllers", ctx.controller_count)
        elif tab == "tab-models":
            return stat("models", ctx.model_count)
        elif tab == "tab-status":
            parts = [stat("apps", ctx.app_count), stat("units", ctx.unit_count)]
            if ctx.machine_count:
                parts.append(stat("machines", ctx.machine_count))
            if ctx.saas_count:
                parts.append(stat("saas", ctx.saas_count))
            if ctx.offer_count:
                parts.append(stat("offers", ctx.offer_count))
            if ctx.relation_count:
                parts.append(stat("relations", ctx.relation_count))
            return "  [dim]·[/dim]  ".join(parts)
        return ""

    def _build_status(self, ctx: HeaderContext) -> str:
        pulse_on = getattr(self, "_pulse_on", True)
        s, off = palette.SUCCESS, palette.PULSE_OFF
        dot = f"[bold {s}]●[/bold {s}]" if pulse_on else f"[{off}]●[/{off}]"
        if ctx.is_connected and ctx.timestamp:
            return f"{dot} [green]Live · {ctx.timestamp}[/green]"
        if ctx.is_connected:
            return f"{dot} [green]Live[/green]"
        return "[red]⚠ Disconnected[/red]"
