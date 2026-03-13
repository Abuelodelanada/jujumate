"""Centralized color palette for JujuMate.

All semantic colors are defined here as module-level constants.
Call ``palette.init(theme)`` at app startup to override the defaults
with the active theme's colors (from the theme YAML ``variables:`` section
and top-level fields).

Usage in Python / Rich markup::

    from jujumate import palette

    text = Text(value, style=palette.LINK)
    markup = f"[{palette.PRIMARY}]{label}[/]"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.theme import Theme

# ── Brand colors ─────────────────────────────────────────────────────────────
PRIMARY = ""
SECONDARY = ""
ACCENT = ""

# ── Semantic status colors ────────────────────────────────────────────────────
SUCCESS = ""
WARNING = ""
ERROR = ""

# ── UI accent colors ──────────────────────────────────────────────────────────
LINK = ""
MUTED = ""

# ── Animation ─────────────────────────────────────────────────────────────────
PULSE_OFF = ""

# ── Log level colors ──────────────────────────────────────────────────────────
LOG_TRACE = ""
LOG_DEBUG = ""
LOG_INFO = ""
LOG_WARNING = ""
LOG_ERROR = ""


def init(theme: Theme) -> None:
    """Override palette globals with the active Textual theme's colors.

    Called once at app startup (``app.on_mount``) after the theme is applied.
    Reads top-level Theme fields (primary, secondary, success, warning, error)
    and ``variables:`` entries (link, muted, pulse-off) from the theme YAML.
    """
    g = globals()
    variables = theme.variables or {}

    color_map = {
        "PRIMARY": theme.primary,
        "SECONDARY": theme.secondary,
        "ACCENT": theme.accent,
        "SUCCESS": theme.success,
        "WARNING": theme.warning,
        "ERROR": theme.error,
        "LINK": variables.get("link"),
        "MUTED": variables.get("muted"),
        "PULSE_OFF": variables.get("pulse-off"),
        "LOG_TRACE": variables.get("log-trace"),
        "LOG_DEBUG": variables.get("log-debug"),
        "LOG_INFO": variables.get("log-info"),
        "LOG_WARNING": variables.get("log-warning") or theme.warning,
        "LOG_ERROR": variables.get("log-error") or theme.error,
    }
    for global_name, value in color_map.items():
        if value:
            g[global_name] = value
