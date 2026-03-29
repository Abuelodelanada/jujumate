"""Modal screen for editing JujuMate settings."""

import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Select, Static

from jujumate import palette
from jujumate.settings import AppSettings, save_settings
from jujumate.theme_loader import load_all_themes

_REFRESH_OPTIONS: list[tuple[str, int]] = [
    ("2 s", 2),
    ("5 s", 5),
    ("10 s", 10),
]
_REFRESH_VALUES: list[int] = [v for _, v in _REFRESH_OPTIONS]

_LOG_OPTIONS: list[tuple[str, int]] = [
    ("DEBUG", logging.DEBUG),
    ("INFO", logging.INFO),
    ("WARNING", logging.WARNING),
    ("ERROR", logging.ERROR),
    ("CRITICAL", logging.CRITICAL),
]

_NO_CONTROLLER = ""


def _nearest_refresh(value: int) -> int:
    """Snap an arbitrary refresh_interval to the nearest allowed option."""
    return min(_REFRESH_VALUES, key=lambda v: abs(v - value))


class SettingsScreen(ModalScreen[AppSettings]):
    """Unified settings modal: Appearance · Behaviour · Diagnostics."""

    BINDINGS = [Binding("escape", "save_and_close", show=False)]

    DEFAULT_CSS = (Path(__file__).parent / "settings_screen.tcss").read_text()

    def __init__(self, settings: AppSettings, controller_names: list[str]) -> None:
        super().__init__()
        self._settings = AppSettings(
            refresh_interval=settings.refresh_interval,
            default_controller=settings.default_controller,
            juju_data_dir=settings.juju_data_dir,
            log_file=settings.log_file,
            log_level=settings.log_level,
            theme=settings.theme,
        )
        self._controller_names = list(controller_names)
        self._original_theme = settings.theme

    def compose(self) -> ComposeResult:
        theme_names = sorted(load_all_themes().keys())
        controller_options: list[tuple[str, str]] = [("— none —", _NO_CONTROLLER)] + [
            (n, n) for n in self._controller_names
        ]
        with Vertical(id="settings-panel"):
            # ── Appearance ────────────────────────────────────────────────
            yield Static(f"  [bold {palette.ACCENT}]Appearance[/]", classes="section-title")
            yield Static(f"  [{palette.MUTED}]{'─' * 50}[/]", classes="section-sep")
            with Horizontal(classes="setting-row"):
                yield Label("Theme", classes="setting-label")
                yield Select(
                    [(n, n) for n in theme_names],
                    value=self._settings.theme,
                    id="select-theme",
                )
            # ── Behaviour ─────────────────────────────────────────────────
            yield Static("", classes="section-spacer")
            yield Static(f"  [bold {palette.ACCENT}]Behaviour[/]", classes="section-title")
            yield Static(f"  [{palette.MUTED}]{'─' * 50}[/]", classes="section-sep")
            with Horizontal(classes="setting-row"):
                yield Label("Refresh interval", classes="setting-label")
                yield Select(
                    _REFRESH_OPTIONS,
                    value=_nearest_refresh(self._settings.refresh_interval),
                    id="select-refresh",
                )
            with Horizontal(classes="setting-row"):
                yield Label("Default controller", classes="setting-label")
                ctrl_value = (
                    self._settings.default_controller
                    if self._settings.default_controller in self._controller_names
                    else _NO_CONTROLLER
                )
                yield Select(
                    controller_options,
                    value=ctrl_value,
                    id="select-controller",
                )
            # ── Diagnostics ───────────────────────────────────────────────
            yield Static("", classes="section-spacer")
            yield Static(f"  [bold {palette.ACCENT}]Diagnostics[/]", classes="section-title")
            yield Static(f"  [{palette.MUTED}]{'─' * 50}[/]", classes="section-sep")
            with Horizontal(classes="setting-row"):
                yield Label("Log level", classes="setting-label")
                yield Select(
                    _LOG_OPTIONS,
                    value=self._settings.log_level,
                    id="select-log-level",
                )
            yield Static(f"  [{palette.MUTED}]Esc  close[/]", id="settings-hint")

    def on_mount(self) -> None:
        self.query_one("#settings-panel").border_title = "Settings"

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        if event.value is Select.BLANK:
            return
        select_id = event.select.id
        if select_id == "select-theme":
            self._settings.theme = str(event.value)
            if hasattr(self.app, "switch_theme"):
                self.app.switch_theme(str(event.value))  # type: ignore[attr-defined]
        elif select_id == "select-refresh":
            self._settings.refresh_interval = int(event.value)  # type: ignore[arg-type]
        elif select_id == "select-controller":
            self._settings.default_controller = str(event.value) if event.value else None
        elif select_id == "select-log-level":
            self._settings.log_level = int(event.value)  # type: ignore[arg-type]
            logging.getLogger().setLevel(int(event.value))  # type: ignore[arg-type]
        save_settings(self._settings)

    def action_save_and_close(self) -> None:
        self.dismiss(self._settings)
