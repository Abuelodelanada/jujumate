import logging
from pathlib import Path

import yaml
from textual.theme import Theme

logger = logging.getLogger(__name__)

BUILTIN_THEMES_DIR = Path(__file__).parent / "themes"
USER_THEMES_DIR = Path.home() / ".config" / "jujumate" / "themes"

_THEME_FIELDS = {
    "primary",
    "secondary",
    "warning",
    "error",
    "success",
    "accent",
    "foreground",
    "background",
    "surface",
    "panel",
    "boost",
    "dark",
    "luminosity_spread",
    "text_alpha",
    "variables",
}


class ThemeError(Exception):
    pass


def _load_theme_file(path: Path) -> Theme:
    with path.open() as f:
        data = yaml.safe_load(f) or {}

    name = data.get("name")
    if not name:
        raise ThemeError(f"Theme file '{path}' is missing required field 'name'.")

    primary = data.get("primary")
    if not primary:
        raise ThemeError(f"Theme file '{path}' is missing required field 'primary'.")

    kwargs = {k: v for k, v in data.items() if k in _THEME_FIELDS}
    return Theme(name=name, **kwargs)


def load_all_themes() -> dict[str, Theme]:
    """Load all built-in themes, then overlay user themes (user takes precedence)."""
    themes: dict[str, Theme] = {}

    for directory in (BUILTIN_THEMES_DIR, USER_THEMES_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.yaml")):
            try:
                theme = _load_theme_file(path)
                themes[theme.name] = theme
                logger.debug("Loaded theme '%s' from %s", theme.name, path)
            except Exception:
                logger.exception("Failed to load theme from '%s'", path)

    return themes


def load_theme(name: str) -> Theme:
    """Load a single theme by name. Raises ThemeError if not found."""
    themes = load_all_themes()
    if name not in themes:
        available = sorted(themes.keys())
        raise ThemeError(f"Theme '{name}' not found. Available themes: {available}")
    return themes[name]
