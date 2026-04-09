"""Modal help overlay showing keyboard shortcuts."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\

[bold cyan]Navigation[/bold cyan]
  [bold]n[/bold]             Navigator (Clouds → Controllers → Models)
  [bold]h[/bold]             Health
  [bold]s[/bold]             Status
  [bold]TAB[/bold]           Move focus to next selector (Navigator) / Switch panels (Status)
  [bold]Shift + TAB[/bold]   Move focus to prev selector (Navigator) / Switch panels (Status)
  [bold]Enter[/bold]         Select item and advance to next selector (Navigator)

[bold cyan]Actions[/bold cyan]
  [bold]/[/bold]             Filter (Status tab) — Esc to clear
  [bold]Enter[/bold]         Drill-down / view app config, relation data or machine detail
  [bold]Esc[/bold]           Clear filter
  [bold]d[/bold]             Toggle detached storage (Status → Storage)
  [bold]f[/bold]             Toggle unhealthy / all models (Health tab)
  [bold]p[/bold]             Toggle peer relations (Status → Integrations)
  [bold]q[/bold]             Quit
  [bold]r[/bold]             Refresh data
  [bold]u[/bold]             Toggle units per machine (Status → Machines)
  [bold]x[/bold]             Collapse/expand current panel (Status)
  [bold]y[/bold]             Copy to clipboard (relation data / status)
  [bold]Shift + c[/bold]     Settings — appearance, behaviour & diagnostics
  [bold]Shift + l[/bold]     Logs — live log stream (requires model selected)
  [bold]Shift + o[/bold]     Offers — all offers across controller
  [bold]Shift + s[/bold]     Secrets (requires model selected)

[bold cyan]Help[/bold cyan]
  [bold]?[/bold]             Toggle this help
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
