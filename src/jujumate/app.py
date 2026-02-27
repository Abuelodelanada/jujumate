import asyncio
import logging
from collections.abc import Sequence

from textual.app import App
from textual.filter import ANSIToTruecolor, LineFilter

from jujumate.screens.main_screen import MainScreen
from jujumate.settings import AppSettings, load_settings
from jujumate.theme_loader import load_all_themes

logger = logging.getLogger(__name__)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Suppress benign cleanup errors from python-libjuju on shutdown."""
    exc = context.get("exception")
    msg = context.get("message", "")
    if isinstance(exc, (RuntimeError, OSError)):
        text = str(exc).lower()
        if "closed" in text or "bad file descriptor" in text or "reuse already awaited" in text:
            return
    if "task was destroyed but it is pending" in msg.lower():
        return
    loop.default_exception_handler(context)


class JujuMateApp(App):
    TITLE = "JujuMate"
    SUB_TITLE = "Juju infrastructure at a glance"
    CSS = """
    * {
        background: ansi_default;
    }
    Screen {
        background: ansi_default;
    }
    Underline > .underline--bar {
        background: ansi_default;
    }
    DataTable {
        background: ansi_default;
    }
    DataTable > .datatable--header {
        background: ansi_default;
    }
    DataTable > .datatable--even-row {
        background: ansi_default;
    }
    DataTable > .datatable--odd-row {
        background: ansi_default;
    }
    DataTable > .datatable--hover {
        background: $primary 20%;
    }
    DataTable > .datatable--cursor {
        background: ansi_default;
    }
    DataTable:focus > .datatable--cursor {
        background: #4D4845;
        text-style: bold;
    }
    """

    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self._settings = settings or load_settings()

    def on_mount(self) -> None:
        asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)
        self._apply_theme()
        logger.info("JujuMate started")
        self.push_screen(MainScreen())

    def get_line_filters(self) -> Sequence[LineFilter]:
        """Exclude ANSIToTruecolor so ansi_default backgrounds emit \\x1b[49m
        (terminal default) preserving terminal transparency."""
        return [f for f in self._filters if f.enabled and not isinstance(f, ANSIToTruecolor)]

    def _apply_theme(self) -> None:
        themes = load_all_themes()
        for theme in themes.values():
            self.register_theme(theme)

        theme_name = self._settings.theme
        if theme_name not in themes:
            fallback = next(iter(themes), None)
            logger.warning("Theme '%s' not found, falling back to '%s'", theme_name, fallback)
            theme_name = fallback

        if theme_name:
            self.theme = theme_name
            logger.info("Applied theme '%s'", theme_name)
