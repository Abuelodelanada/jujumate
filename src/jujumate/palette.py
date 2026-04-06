"""Centralized color palette for JujuMate.

All semantic colors are defined here as module-level constants backed by a
private ``_Palette`` dataclass instance.  Call ``palette.init(theme)`` at app
startup to populate the defaults with the active theme's colors.

Usage in Python / Rich markup::

    from jujumate import palette

    text = Text(value, style=palette.LINK)
    markup = f"[{palette.PRIMARY}]{label}[/]"
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.theme import Theme


@dataclass
class _Palette:
    # ── Brand colors ─────────────────────────────────────────────────────────
    PRIMARY: str = ""
    SECONDARY: str = ""
    ACCENT: str = ""

    # ── Semantic status colors ────────────────────────────────────────────────
    SUCCESS: str = ""
    WARNING: str = ""
    BLOCKED: str = ""
    ERROR: str = ""

    # ── UI accent colors ──────────────────────────────────────────────────────
    LINK: str = ""
    MUTED: str = ""

    # ── Animation ─────────────────────────────────────────────────────────────
    PULSE_OFF: str = ""

    # ── Log level colors ──────────────────────────────────────────────────────
    LOG_TRACE: str = ""
    LOG_DEBUG: str = ""
    LOG_INFO: str = ""
    LOG_WARNING: str = ""
    LOG_ERROR: str = ""


_palette = _Palette()

# Names exported as module-level constants via __getattr__ (PEP 562).
_FIELD_NAMES: frozenset[str] = frozenset(f.name for f in fields(_Palette))


def __getattr__(name: str) -> str:
    if name in _FIELD_NAMES:
        return getattr(_palette, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_STATUS_COLORS: dict[str, str] = {
    "active": "SUCCESS",
    "idle": "SUCCESS",
    "started": "SUCCESS",
    "attached": "SUCCESS",
    "alive": "SUCCESS",
    "blocked": "BLOCKED",
    "error": "ERROR",
    "terminated": "ERROR",
    "dead": "ERROR",
    "detached": "WARNING",
    "dying": "WARNING",
    "maintenance": "WARNING",
    "waiting": "WARNING",
    "executing": "WARNING",
    "unknown": "MUTED",
}


def status_color(status: str) -> str:
    """Return the palette color string for a given Juju status value.

    Returns an empty string for unrecognised statuses (caller renders plain text).
    """
    attr = _STATUS_COLORS.get(status.strip().lower(), "")
    return getattr(_palette, attr) if attr else ""


def init(theme: Theme) -> None:
    """Populate palette values from the active Textual theme.

    Called once at app startup (``app.on_mount``) after the theme is applied.
    Reads top-level Theme fields (primary, secondary, success, warning, error)
    and ``variables:`` entries (link, muted, pulse-off) from the theme YAML.
    """
    variables = theme.variables or {}

    color_map = {
        "PRIMARY": theme.primary,
        "SECONDARY": theme.secondary,
        "ACCENT": theme.accent,
        "SUCCESS": theme.success,
        "WARNING": theme.warning,
        "BLOCKED": variables.get("blocked") or "#FF8800",
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
    for name, value in color_map.items():
        if value:
            setattr(_palette, name, value)
