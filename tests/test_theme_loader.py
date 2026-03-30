import pytest
import yaml

from jujumate.theme_loader import ThemeError, load_all_themes, load_theme


def _write_theme(directory, data):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{data['name']}.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def user_themes_dir(tmp_path, monkeypatch):
    """Redirect USER_THEMES_DIR to a temporary directory and return it."""
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize("theme_name", ["ubuntu", "dark"])
def test_builtin_themes_include(theme_name: str) -> None:
    # GIVEN the set of all installed themes
    # WHEN we load all themes
    themes = load_all_themes()
    # THEN the expected built-in theme is present
    assert theme_name in themes


def test_load_theme_ubuntu():
    # GIVEN the built-in ubuntu theme exists
    # WHEN we load it by name
    theme = load_theme("ubuntu")
    # THEN its name and primary colour match the expected values
    assert theme.name == "ubuntu"
    assert theme.primary == "#E95420"


def test_load_theme_not_found_raises():
    # GIVEN a theme name that does not exist
    # WHEN we try to load it
    # THEN a ThemeError is raised with "not found" in the message
    with pytest.raises(ThemeError, match="not found"):
        load_theme("nonexistent-theme")


def test_user_theme_overrides_builtin(user_themes_dir):
    # GIVEN a user theme file named "ubuntu" with a different primary colour
    _write_theme(user_themes_dir, {"name": "ubuntu", "primary": "#FF0000"})

    # WHEN we load the "ubuntu" theme
    theme = load_theme("ubuntu")

    # THEN the user's version takes precedence
    assert theme.primary == "#FF0000"


def test_user_custom_theme_is_available(user_themes_dir):
    # GIVEN a user-defined theme file that doesn't exist in builtins
    _write_theme(user_themes_dir, {"name": "mytheme", "primary": "#AABBCC"})

    # WHEN we load all themes
    themes = load_all_themes()

    # THEN the custom theme appears in the result
    assert "mytheme" in themes


def test_theme_missing_name_raises(user_themes_dir):
    # GIVEN a YAML theme file that is missing the "name" field
    bad = user_themes_dir / "bad.yaml"
    bad.write_text(yaml.dump({"primary": "#FF0000"}))

    # WHEN we load all themes
    themes = load_all_themes()

    # THEN the bad theme is silently skipped
    assert "bad" not in themes


def test_theme_missing_primary_raises(user_themes_dir):
    # GIVEN a YAML theme file that is missing the "primary" field
    bad = user_themes_dir / "noprimary.yaml"
    bad.write_text(yaml.dump({"name": "noprimary"}))

    # WHEN we load all themes
    themes = load_all_themes()

    # THEN the bad theme is silently skipped
    assert "noprimary" not in themes


def test_invalid_yaml_skipped(user_themes_dir):
    # GIVEN a theme file containing invalid YAML
    bad = user_themes_dir / "broken.yaml"
    bad.write_text(":::: not valid yaml ::::")

    # WHEN we load all themes
    themes = load_all_themes()

    # THEN the broken file is silently skipped
    assert "broken" not in themes


def test_unreadable_file_skipped(user_themes_dir):
    # GIVEN a theme file that cannot be read (no read permission)
    bad = user_themes_dir / "locked.yaml"
    bad.write_text(yaml.dump({"name": "locked", "primary": "#FF0000"}))
    bad.chmod(0o000)

    # WHEN we load all themes
    themes = load_all_themes()

    # THEN the unreadable file is silently skipped
    assert "locked" not in themes

    bad.chmod(0o644)  # restore so tmp_path cleanup doesn't fail
