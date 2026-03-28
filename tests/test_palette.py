"""Tests for palette.py — verifies that all built-in themes define every
variable required by palette.init(), so no palette global is ever left empty."""

import pytest

from jujumate import palette
from jujumate.theme_loader import load_all_themes

# Variables that every theme MUST define for palette.init() to fully populate.
_REQUIRED_TOP_LEVEL = {"primary", "secondary", "success", "warning", "error"}
_REQUIRED_VARIABLES = {"link", "muted", "pulse-off", "log-trace", "log-debug", "log-info"}


def _builtin_theme_names() -> list[str]:
    return sorted(load_all_themes().keys())


@pytest.mark.parametrize("theme_name", _builtin_theme_names())
def test_theme_defines_required_top_level_colors(theme_name: str) -> None:
    # GIVEN a built-in theme
    theme = load_all_themes()[theme_name]
    # WHEN we inspect each required top-level field
    # THEN every required field is present and non-empty
    for field in _REQUIRED_TOP_LEVEL:
        value = getattr(theme, field, None)
        assert value, f"Theme '{theme_name}' is missing required field '{field}'"


@pytest.mark.parametrize("theme_name", _builtin_theme_names())
def test_theme_defines_required_variables(theme_name: str) -> None:
    # GIVEN a built-in theme
    theme = load_all_themes()[theme_name]
    # WHEN we inspect the variables dict
    variables = theme.variables or {}
    # THEN every required variable key is present
    for key in _REQUIRED_VARIABLES:
        assert key in variables, f"Theme '{theme_name}' is missing required variable '{key}'"


@pytest.mark.parametrize("theme_name", _builtin_theme_names())
def test_palette_init_populates_all_globals(theme_name: str) -> None:
    # GIVEN a built-in theme
    theme = load_all_themes()[theme_name]
    # WHEN palette.init() is called with that theme
    palette.init(theme)
    # THEN all palette globals are non-empty
    assert palette.PRIMARY, f"palette.PRIMARY is empty after init with theme '{theme_name}'"
    assert palette.SECONDARY, f"palette.SECONDARY is empty after init with theme '{theme_name}'"
    assert palette.SUCCESS, f"palette.SUCCESS is empty after init with theme '{theme_name}'"
    assert palette.WARNING, f"palette.WARNING is empty after init with theme '{theme_name}'"
    assert palette.BLOCKED, f"palette.BLOCKED is empty after init with theme '{theme_name}'"
    assert palette.ERROR, f"palette.ERROR is empty after init with theme '{theme_name}'"
    assert palette.LINK, f"palette.LINK is empty after init with theme '{theme_name}'"
    assert palette.MUTED, f"palette.MUTED is empty after init with theme '{theme_name}'"
    assert palette.PULSE_OFF, f"palette.PULSE_OFF is empty after init with theme '{theme_name}'"
    assert palette.LOG_TRACE, f"palette.LOG_TRACE is empty after init with theme '{theme_name}'"
    assert palette.LOG_DEBUG, f"palette.LOG_DEBUG is empty after init with theme '{theme_name}'"
    assert palette.LOG_INFO, f"palette.LOG_INFO is empty after init with theme '{theme_name}'"
    assert palette.LOG_WARNING, f"palette.LOG_WARNING is empty after init with theme '{theme_name}'"
    assert palette.LOG_ERROR, f"palette.LOG_ERROR is empty after init with theme '{theme_name}'"
