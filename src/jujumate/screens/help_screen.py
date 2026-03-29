"""Modal help overlay showing keyboard shortcuts."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\

[bold cyan]Navigation[/bold cyan]
  [bold]c[/bold]       Clouds
  [bold]m[/bold]       Models
  [bold]s[/bold]       Status
  [bold]h[/bold]       Health

[bold cyan]Actions[/bold cyan]
  [bold]Enter[/bold]   Drill-down / view app config, relation data or machine detail
  [bold]/[/bold]       Filter (Status tab) — Esc to clear
  [bold]f[/bold]       Toggle unhealthy / all models (Health tab)
  [bold]S[/bold]       Secrets (requires model selected)
  [bold]O[/bold]       Offers — all offers across controller
  [bold]L[/bold]       Logs — live log stream (requires model selected)
  [bold]C[/bold]       Settings — appearance, behaviour & diagnostics
  [bold]r[/bold]       Refresh data
  [bold]y[/bold]       Copy to clipboard (relation data / status)
  [bold]p[/bold]       Toggle peer relations (Status → Integrations)
  [bold]u[/bold]       Toggle units per machine (Status → Machines)
  [bold]Esc[/bold]     Clear filter
  [bold]q[/bold]       Quit

[bold cyan]Help[/bold cyan]
  [bold]?[/bold]       Toggle this help
"""


class HelpScreen(ModalScreen):
    """Transparent modal overlay that displays keybindings."""

    BINDINGS = [
        Binding("question_mark", "dismiss", "Close help", show=False),
        Binding("escape", "dismiss", "Close help", show=False),
    ]

    DEFAULT_CSS = (Path(__file__).parent / "help_screen.tcss").read_text()

    def compose(self) -> ComposeResult:
        panel = Static(HELP_TEXT, id="help-panel")
        panel.border_title = "Keyboard Shortcuts"
        yield panel
