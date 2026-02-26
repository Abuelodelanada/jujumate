import asyncio
import logging

from textual.app import App

from jujumate.screens.main_screen import MainScreen
from jujumate.settings import AppSettings, load_settings
from jujumate.theme_loader import load_all_themes

logger = logging.getLogger(__name__)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Suppress benign SSL/WebSocket cleanup errors from python-libjuju on shutdown."""
    exc = context.get("exception")
    if isinstance(exc, (RuntimeError, OSError)):
        msg = str(exc).lower()
        if "closed" in msg or "bad file descriptor" in msg:
            return
    loop.default_exception_handler(context)


class JujuMateApp(App):
    TITLE = "JujuMate"
    SUB_TITLE = "Juju infrastructure at a glance"

    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self._settings = settings or load_settings()

    def on_mount(self) -> None:
        asyncio.get_event_loop().set_exception_handler(_asyncio_exception_handler)
        self._apply_theme()
        logger.info("JujuMate started")
        self.push_screen(MainScreen())

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
