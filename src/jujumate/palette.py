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

# ── Semantic status colors ────────────────────────────────────────────────────
SUCCESS = ""
WARNING = ""
ERROR = ""

# ── UI accent colors ──────────────────────────────────────────────────────────
LINK = ""
MUTED = ""

# ── Animation ─────────────────────────────────────────────────────────────────
PULSE_OFF = ""


def init(theme: Theme) -> None:
    """Override palette globals with the active Textual theme's colors.

    Called once at app startup (``app.on_mount``) after the theme is applied.
    Reads top-level Theme fields (primary, secondary, success, warning, error)
    and ``variables:`` entries (link, muted, pulse-off) from the theme YAML.
    """
    g = globals()

    if theme.primary:
        g["PRIMARY"] = theme.primary
    if theme.secondary:
        g["SECONDARY"] = theme.secondary
    if theme.success:
        g["SUCCESS"] = theme.success
    if theme.warning:
        g["WARNING"] = theme.warning
    if theme.error:
        g["ERROR"] = theme.error

    variables = theme.variables or {}
    if "link" in variables:
        g["LINK"] = variables["link"]
    if "muted" in variables:
        g["MUTED"] = variables["muted"]
    if "pulse-off" in variables:
        g["PULSE_OFF"] = variables["pulse-off"]
