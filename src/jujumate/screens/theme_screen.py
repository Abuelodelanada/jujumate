"""Modal screen for switching themes at runtime with live preview."""

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Label, ListItem, ListView

from jujumate.settings import save_theme
from jujumate.theme_loader import load_all_themes

logger = logging.getLogger(__name__)

_SWATCH_ATTRS = ("background", "primary", "secondary", "success", "error")
_SWATCH_FALLBACK = "#555555"


def _swatches(theme: Theme) -> str:
    """Return Rich markup for 5 colored block swatches (bg, primary, secondary, success, error)."""
    parts = []
    for attr in _SWATCH_ATTRS:
        color = getattr(theme, attr, None) or _SWATCH_FALLBACK
        parts.append(f"[on {color}]  [/]")
    return " ".join(parts)


class ThemeScreen(ModalScreen):
    """Modal overlay for selecting a theme. Previews each theme live as you navigate."""

    BINDINGS = [Binding("escape", "cancel", show=False)]

    DEFAULT_CSS = """
    ThemeScreen {
        align: center middle;
    }
    ThemeScreen #theme-panel {
        width: 52;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $accent;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }
    ThemeScreen ListView {
        height: auto;
        max-height: 16;
        background: transparent;
    }
    ThemeScreen #theme-hint {
        height: 1;
        margin-top: 1;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._themes = load_all_themes()
        self._theme_names = sorted(self._themes.keys())
        self._original_theme: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-panel"):
            yield ListView(
                *[
                    ListItem(
                        Label(f"{name:<18} {_swatches(self._themes[name])}"),
                        name=name,
                    )
                    for name in self._theme_names
                ],
                id="theme-list",
            )
            yield Label(
                "[bold]Enter[/bold] apply & save  ·  [bold]Esc[/bold] cancel",
                id="theme-hint",
            )

    def on_mount(self) -> None:
        self._original_theme = self.app.theme or ""
        self.query_one("#theme-panel").border_title = "Theme"
        lv = self.query_one("#theme-list", ListView)
        if self._original_theme in self._theme_names:
            lv.index = self._theme_names.index(self._original_theme)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        name = event.item.name if event.item else None
        if name and name in self._themes and hasattr(self.app, "switch_theme"):
            self.app.switch_theme(name)  # type: ignore[attr-defined]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = event.item.name if event.item else None
        if name and name in self._themes:
            # Theme already previewed via on_list_view_highlighted; just persist and close.
            save_theme(name)
            self.dismiss()

    def action_cancel(self) -> None:
        if self._original_theme and hasattr(self.app, "switch_theme"):
            self.app.switch_theme(self._original_theme)  # type: ignore[attr-defined]
        self.dismiss()
