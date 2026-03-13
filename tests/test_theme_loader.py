import pytest
import yaml

from jujumate.theme_loader import ThemeError, load_all_themes, load_theme


def _write_theme(directory, data):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{data['name']}.yaml"
    path.write_text(yaml.dump(data))
    return path


def test_builtin_themes_include_ubuntu():
    themes = load_all_themes()
    assert "ubuntu" in themes


def test_builtin_themes_include_dark():
    themes = load_all_themes()
    assert "dark" in themes


def test_load_theme_ubuntu():
    theme = load_theme("ubuntu")
    assert theme.name == "ubuntu"
    assert theme.primary == "#E95420"


def test_load_theme_not_found_raises():
    with pytest.raises(ThemeError, match="not found"):
        load_theme("nonexistent-theme")


def test_user_theme_overrides_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    _write_theme(tmp_path, {"name": "ubuntu", "primary": "#FF0000"})

    theme = load_theme("ubuntu")
    assert theme.primary == "#FF0000"


def test_user_custom_theme_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    _write_theme(tmp_path, {"name": "mytheme", "primary": "#AABBCC"})

    themes = load_all_themes()
    assert "mytheme" in themes


def test_theme_missing_name_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump({"primary": "#FF0000"}))

    # bad theme is skipped (logged), doesn't crash load_all_themes
    themes = load_all_themes()
    assert "bad" not in themes


def test_theme_missing_primary_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    bad = tmp_path / "noprimary.yaml"
    bad.write_text(yaml.dump({"name": "noprimary"}))

    themes = load_all_themes()
    assert "noprimary" not in themes


def test_invalid_yaml_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    bad = tmp_path / "broken.yaml"
    bad.write_text(":::: not valid yaml ::::")

    themes = load_all_themes()
    assert "broken" not in themes


def test_unreadable_file_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr("jujumate.theme_loader.USER_THEMES_DIR", tmp_path)
    bad = tmp_path / "locked.yaml"
    bad.write_text(yaml.dump({"name": "locked", "primary": "#FF0000"}))
    bad.chmod(0o000)

    themes = load_all_themes()
    assert "locked" not in themes

    bad.chmod(0o644)  # restore so tmp_path cleanup doesn't fail
