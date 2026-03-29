"""Modal screen showing detailed information for a single Juju machine."""

import re
from datetime import datetime, timezone
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from jujumate import palette
from jujumate.models.entities import MachineInfo


def _normalize_iso(iso_str: str) -> str:
    """Normalize an ISO 8601 string for Python 3.10 fromisoformat compatibility.

    Handles two edge cases that Python 3.10 can't parse:
    - Nanosecond precision (9 fractional digits) — truncated to 6 (microseconds)
    - UTC 'Z' suffix — replaced with '+00:00'
    """
    s = iso_str.replace("Z", "+00:00")
    return re.sub(r"(\.\d{6})\d+", r"\1", s)


def _time_ago(iso_str: str) -> str:
    """Return a human-readable relative time string from an ISO 8601 timestamp."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(_normalize_iso(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            return ""
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return iso_str


def _fmt_ts(iso_str: str) -> str:
    """Format an ISO 8601 timestamp as 'YYYY-MM-DD HH:MM:SS', dropping microseconds."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(_normalize_iso(iso_str))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_str


def _row(label: str, value: str, label_width: int = 16) -> str:
    """Format a single label/value row with consistent alignment."""
    padded = label.ljust(label_width)
    return f"  [bold]{padded}[/bold]{value}"


class MachineDetailScreen(ModalScreen):
    """Full-detail modal for a single Juju machine."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]
    DEFAULT_CSS = (Path(__file__).parent / "machine_detail_screen.tcss").read_text()

    def __init__(self, machine: MachineInfo) -> None:
        super().__init__()
        self._machine = machine

    def compose(self) -> ComposeResult:
        panel = Static(self._build_content(), id="machine-detail-panel")
        panel.border_title = f"Machine {self._machine.id}"
        yield panel

    def _render_section(self, title: str, rows: list[tuple[str, str]]) -> list[str]:
        """Render a titled section with a separator and uniformly formatted rows."""
        lines: list[str] = [
            "",
            f"  [bold {palette.ACCENT}]{title}[/]",
            f"  [{palette.MUTED}]{'─' * 44}[/]",
        ]
        lines += [_row(label, value) for label, value in rows]
        return lines

    def _section_meta(self) -> list[str]:
        m = self._machine
        address = f"[{palette.LINK}]{m.address}[/]" if m.address else "—"
        return [
            _row("Instance ID", m.instance_id or "—"),
            _row("Address", address),
            _row("Base", m.base or "—"),
            _row("AZ", m.az or "—"),
            _row("Controller", m.controller or "—"),
            _row("Model", m.model or "—"),
        ]

    def _section_hardware(self) -> list[str]:
        m = self._machine
        rows: list[tuple[str, str]] = []
        if m.hardware_arch:
            rows.append(("Arch", m.hardware_arch))
        if m.hardware_cores:
            rows.append(("CPU Cores", str(m.hardware_cores)))
        if m.hardware_mem_mib:
            mem = f"{m.hardware_mem_mib} MiB  ({m.hardware_mem_mib / 1024:.1f} GiB)"
            rows.append(("Memory", mem))
        if m.hardware_disk_mib:
            disk = f"{m.hardware_disk_mib} MiB  ({m.hardware_disk_mib / 1024:.1f} GiB)"
            rows.append(("Root Disk", disk))
        if m.hardware_virt_type:
            rows.append(("Virt Type", m.hardware_virt_type))
        if not rows:
            return []
        return self._render_section("Hardware", rows)

    def _section_status(self) -> list[str]:
        m = self._machine
        agent_ago = _time_ago(m.agent_since)
        inst_ago = _time_ago(m.instance_since)

        def _colored(s: str) -> str:
            color = palette.status_color(s)
            return f"[{color}]{s}[/]" if color else s

        agent_parts = [
            _colored(m.state),
            _fmt_ts(m.agent_since),
            f"({agent_ago})" if agent_ago else "",
        ]
        inst_parts = [
            _colored(m.instance_status or "—"),
            _fmt_ts(m.instance_since),
            f"({inst_ago})" if inst_ago else "",
        ]
        rows: list[tuple[str, str]] = [
            ("Agent", "  ".join(p for p in agent_parts if p)),
            ("Instance", "  ".join(p for p in inst_parts if p)),
        ]
        if m.message:
            rows.append(("Message", m.message))
        return self._render_section("Status", rows)

    def _section_network(self) -> list[str]:
        m = self._machine
        if not m.network_interfaces:
            return []
        lines: list[str] = [
            "",
            f"  [bold {palette.ACCENT}]Network Interfaces[/]",
            f"  [{palette.MUTED}]{'─' * 44}[/]",
        ]
        for iface in m.network_interfaces:
            lines.append(f"  [{palette.MUTED}]── {iface.name}[/]")
            for i, ip in enumerate(iface.ips):
                lines.append(_row("IPs" if i == 0 else "", ip))
            if not iface.ips:
                lines.append(_row("IPs", "—"))
            lines.append(_row("MAC", iface.mac or "—"))
            if iface.space:
                lines.append(_row("Space", iface.space))
        return lines

    def _build_content(self) -> str:
        sections = [
            self._section_meta(),
            self._section_hardware(),
            self._section_status(),
            self._section_network(),
        ]
        return "\n".join(line for section in sections for line in section)
