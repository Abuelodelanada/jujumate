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

    def _build_content(self) -> str:
        m = self._machine
        lines: list[str] = []

        lines.append(_row("Instance ID", m.instance_id or "—"))
        lines.append(_row("Address", m.address or "—"))
        lines.append(_row("Base", m.base or "—"))
        lines.append(_row("AZ", m.az or "—"))
        lines.append(_row("Controller", m.controller or "—"))
        lines.append(_row("Model", m.model or "—"))

        has_hw = any(
            [
                m.hardware_arch,
                m.hardware_cores,
                m.hardware_mem_mib,
                m.hardware_disk_mib,
                m.hardware_virt_type,
            ]
        )
        if has_hw:
            lines.append("")
            lines.append(f"  [bold {palette.ACCENT}]Hardware[/]")
            lines.append(f"  [{palette.MUTED}]{'─' * 44}[/]")
            if m.hardware_arch:
                lines.append(_row("Arch", m.hardware_arch))
            if m.hardware_cores:
                lines.append(_row("CPU Cores", str(m.hardware_cores)))
            if m.hardware_mem_mib:
                mem = f"{m.hardware_mem_mib} MiB  ({m.hardware_mem_mib / 1024:.1f} GiB)"
                lines.append(_row("Memory", mem))
            if m.hardware_disk_mib:
                disk = f"{m.hardware_disk_mib} MiB  ({m.hardware_disk_mib / 1024:.1f} GiB)"
                lines.append(_row("Root Disk", disk))
            if m.hardware_virt_type:
                lines.append(_row("Virt Type", m.hardware_virt_type))

        lines.append("")
        lines.append(f"  [bold {palette.ACCENT}]Status[/]")
        lines.append(f"  [{palette.MUTED}]{'─' * 44}[/]")
        agent_ago = _time_ago(m.agent_since)
        inst_ago = _time_ago(m.instance_since)
        agent_ts = _fmt_ts(m.agent_since)
        inst_ts = _fmt_ts(m.instance_since)
        agent_parts = [m.state, agent_ts, f"({agent_ago})" if agent_ago else ""]
        inst_parts = [(m.instance_status or "—"), inst_ts, f"({inst_ago})" if inst_ago else ""]
        lines.append(_row("Agent", "  ".join(p for p in agent_parts if p)))
        lines.append(_row("Instance", "  ".join(p for p in inst_parts if p)))
        if m.message:
            lines.append(_row("Message", m.message))

        if m.network_interfaces:
            lines.append("")
            lines.append(f"  [bold {palette.ACCENT}]Network Interfaces[/]")
            lines.append(f"  [{palette.MUTED}]{'─' * 44}[/]")
            for iface in m.network_interfaces:
                lines.append(f"  [{palette.MUTED}]── {iface.name}[/]")
                for i, ip in enumerate(iface.ips):
                    lines.append(_row("IPs" if i == 0 else "", ip))
                if not iface.ips:
                    lines.append(_row("IPs", "—"))
                lines.append(_row("MAC", iface.mac or "—"))
                if iface.space:
                    lines.append(_row("Space", iface.space))

        return "\n".join(lines)
