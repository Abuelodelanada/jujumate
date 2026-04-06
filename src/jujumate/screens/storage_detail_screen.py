"""Modal screen showing detailed information for a single Juju storage instance."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from jujumate import palette
from jujumate.client.juju_client import _format_size_mib
from jujumate.models.entities import StorageInfo


def _row(label: str, value: str, label_width: int = 14) -> str:
    """Format a single label/value row with consistent alignment."""
    padded = label.ljust(label_width)
    return f"  [bold]{padded}[/bold]{value}"


class StorageDetailScreen(ModalScreen):
    """Full-detail modal for a single Juju storage instance."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]
    DEFAULT_CSS = (Path(__file__).parent / "storage_detail_screen.tcss").read_text()

    def __init__(self, storage: StorageInfo) -> None:
        super().__init__()
        self._storage = storage

    def compose(self) -> ComposeResult:
        panel = Static(self._build_content(), id="storage-detail-panel")
        panel.border_title = f"Storage  {self._storage.storage_id}"
        yield panel

    def _build_content(self) -> str:
        s = self._storage
        lines: list[str] = []

        def _bool(v: bool) -> str:
            color = palette.SUCCESS if v else palette.MUTED
            return f"[{color}]{'yes' if v else 'no'}[/]"

        def _status(v: str) -> str:
            color = palette.status_color(v)
            return f"[{color}]{v}[/]" if color else v

        lines += [
            _row("Unit", s.unit or "—"),
            _row("Storage ID", s.storage_id),
            _row("Type", s.kind),
            _row("Pool", s.pool or "—"),
            _row("Size", _format_size_mib(s.size_mib) or "—"),
            _row("Status", _status(s.status) if s.status else "—"),
        ]

        if s.message:
            lines.append(_row("Message", s.message))

        lines += [
            "",
            f"  [bold {palette.ACCENT}]Attachment[/]",
            f"  [{palette.MUTED}]{'─' * 44}[/]",
            _row("Mountpoint", s.location or "—"),
            _row("Read Only", _bool(s.read_only)),
        ]
        if s.device_name:
            lines.append(_row("Device", s.device_name))
        if s.device_link:
            lines.append(_row("Device Link", s.device_link))
        lines += [
            "",
            f"  [bold {palette.ACCENT}]Lifecycle[/]",
            f"  [{palette.MUTED}]{'─' * 44}[/]",
            _row("Persistent", _bool(s.persistent)),
        ]
        life_val = s.life or "—"
        if s.life:
            color = palette.status_color(s.life)
            life_val = f"[{color}]{s.life}[/]" if color else s.life
        lines.append(_row("Life", life_val))

        return "\n".join(lines)
