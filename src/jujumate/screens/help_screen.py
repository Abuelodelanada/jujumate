"""Modal help overlay showing keyboard shortcuts."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\
[bold]Keyboard Shortcuts[/bold]

[bold cyan]Navigation[/bold cyan]
  [bold]c[/bold]       Clouds
  [bold]C[/bold]       Controllers
  [bold]m[/bold]       Models
  [bold]s[/bold]       Status

[bold cyan]Actions[/bold cyan]
  [bold]Enter[/bold]   Drill-down / view app config or relation data
  [bold]/[/bold]       Filter (Status tab) — Esc to clear
  [bold]S[/bold]       Secrets (requires model selected)
  [bold]r[/bold]       Refresh data
  [bold]y[/bold]       Copy relation data to clipboard
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

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen #help-panel {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(HELP_TEXT, id="help-panel")
