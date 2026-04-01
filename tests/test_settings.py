import logging

import pytest
import yaml

from jujumate.settings import (
    AppSettings,
    AppSettingsError,
    load_settings,
    save_settings,
    save_theme,
)


def _write_config(tmp_path, data):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


def test_defaults_when_file_missing(tmp_path):
    # GIVEN no config file exists at the given path
    # WHEN load_settings is called
    settings = load_settings(tmp_path / "config.yaml")
    # THEN default values are returned
    assert settings.refresh_interval == 5
    assert settings.offers_cache_ttl == 300
    assert settings.default_controller is None


@pytest.mark.parametrize(
    "yaml_data,attr,expected",
    [
        pytest.param(
            {"refresh_interval": 10},
            "refresh_interval",
            10,
            id="refresh_interval",
        ),
        pytest.param(
            {"offers_cache_ttl": 120},
            "offers_cache_ttl",
            120,
            id="offers_cache_ttl",
        ),
        pytest.param(
            {"default_controller": "prod"},
            "default_controller",
            "prod",
            id="default_controller",
        ),
        pytest.param(
            None,  # juju_data_dir uses tmp_path directly — handled below
            "juju_data_dir",
            None,  # sentinel — checked specially
            id="juju_data_dir",
        ),
        pytest.param(
            None,  # log_file uses tmp_path directly — handled below
            "log_file",
            None,  # sentinel — checked specially
            id="log_file",
        ),
    ],
)
def test_custom_setting(tmp_path, yaml_data, attr, expected):
    # GIVEN a config file with a custom setting
    if attr == "juju_data_dir":
        config_file = _write_config(tmp_path, {"juju_data_dir": str(tmp_path)})
        # WHEN load_settings is called
        settings = load_settings(config_file)
        # THEN the juju_data_dir is set to the given path
        assert settings.juju_data_dir == tmp_path
        return
    if attr == "log_file":
        config_file = _write_config(tmp_path, {"log_file": str(tmp_path / "app.log")})
        # WHEN load_settings is called
        settings = load_settings(config_file)
        # THEN the log_file is set to the given path
        assert settings.log_file == tmp_path / "app.log"
        return
    config_file = _write_config(tmp_path, yaml_data)
    # WHEN load_settings is called
    settings = load_settings(config_file)
    # THEN the expected attribute has the expected value
    assert getattr(settings, attr) == expected


def test_invalid_refresh_interval_raises(tmp_path):
    # GIVEN a config file with refresh_interval set to 0 (invalid)
    config_file = _write_config(tmp_path, {"refresh_interval": 0})
    # WHEN load_settings is called
    # THEN an AppSettingsError is raised mentioning refresh_interval
    with pytest.raises(AppSettingsError, match="refresh_interval"):
        load_settings(config_file)


def test_non_integer_refresh_interval_raises(tmp_path):
    # GIVEN a config file with a non-integer refresh_interval
    config_file = _write_config(tmp_path, {"refresh_interval": "fast"})
    # WHEN load_settings is called
    # THEN an AppSettingsError is raised mentioning refresh_interval
    with pytest.raises(AppSettingsError, match="refresh_interval"):
        load_settings(config_file)


@pytest.mark.parametrize(
    "value",
    [pytest.param(0, id="zero"), pytest.param("slow", id="string")],
)
def test_invalid_offers_cache_ttl_raises(tmp_path, value):
    # GIVEN a config file with an invalid offers_cache_ttl
    config_file = _write_config(tmp_path, {"offers_cache_ttl": value})
    # WHEN load_settings is called
    # THEN an AppSettingsError is raised mentioning offers_cache_ttl
    with pytest.raises(AppSettingsError, match="offers_cache_ttl"):
        load_settings(config_file)


def test_empty_file_returns_defaults(tmp_path):
    # GIVEN a config file that exists but is empty
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    # WHEN load_settings is called
    settings = load_settings(config_file)
    # THEN default values are returned
    assert settings.refresh_interval == 5


@pytest.mark.parametrize(
    "yaml_data, expected_level, raises",
    [
        pytest.param(None, logging.INFO, False, id="default"),
        pytest.param({"log_level": "DEBUG"}, logging.DEBUG, False, id="custom-debug"),
        pytest.param({"log_level": "info"}, logging.INFO, False, id="case-insensitive"),
        pytest.param({"log_level": "VERBOSE"}, None, True, id="invalid-raises"),
    ],
)
def test_log_level(tmp_path, yaml_data, expected_level, raises):
    # GIVEN a config file (or none) with the given log_level setting
    if yaml_data is None:
        config_file = tmp_path / "config.yaml"
    else:
        config_file = _write_config(tmp_path, yaml_data)

    # WHEN load_settings is called
    if raises:
        # THEN an AppSettingsError is raised for unrecognised levels
        with pytest.raises(AppSettingsError, match="log_level"):
            load_settings(config_file)
    else:
        settings = load_settings(config_file)
        # THEN the resolved log level matches expectations
        assert settings.log_level == expected_level


def test_save_theme_creates_file(tmp_path):
    # GIVEN no config file exists
    config_file = tmp_path / "config.yaml"
    assert not config_file.exists()

    # WHEN save_theme is called
    save_theme("ubuntu", config_file=config_file)

    # THEN the file is created and contains the theme value
    assert config_file.exists()
    data = yaml.safe_load(config_file.read_text())
    assert data["theme"] == "ubuntu"


def test_save_theme_preserves_existing_settings(tmp_path):
    # GIVEN a config file that already contains a refresh_interval setting
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"refresh_interval": 10}))

    # WHEN save_theme is called with a new theme name
    save_theme("ubuntu", config_file=config_file)

    # THEN both the new theme and the existing setting are present
    data = yaml.safe_load(config_file.read_text())
    assert data["theme"] == "ubuntu"
    assert data["refresh_interval"] == 10


# ─────────────────────────────────────────────────────────────────────────────
# save_settings
# ─────────────────────────────────────────────────────────────────────────────


def _default_settings(**kwargs) -> AppSettings:
    defaults = dict(refresh_interval=5, log_level=logging.INFO, theme="ubuntu")
    defaults.update(kwargs)
    return AppSettings(**defaults)


def test_save_settings_creates_file_with_all_fields(tmp_path):
    # GIVEN no config file and a fully populated AppSettings
    config_file = tmp_path / "config.yaml"
    settings = _default_settings(
        refresh_interval=10, default_controller="prod", log_level=logging.DEBUG, theme="dark"
    )
    # WHEN save_settings is called
    save_settings(settings, config_file=config_file)
    # THEN the file is created with all persisted fields
    data = yaml.safe_load(config_file.read_text())
    assert data["theme"] == "dark"
    assert data["refresh_interval"] == 10
    assert data["default_controller"] == "prod"
    assert data["log_level"] == "DEBUG"


def test_save_settings_removes_default_controller_when_none(tmp_path):
    # GIVEN a config file that already has a default_controller
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"default_controller": "old-ctrl"}))
    settings = _default_settings(default_controller=None)
    # WHEN save_settings is called with default_controller=None
    save_settings(settings, config_file=config_file)
    # THEN default_controller is removed from the file
    data = yaml.safe_load(config_file.read_text())
    assert "default_controller" not in data


def test_save_settings_preserves_unmanaged_keys(tmp_path):
    # GIVEN a config file with juju_data_dir (an unmanaged key for save_settings)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump({"juju_data_dir": "/custom/path"}))
    settings = _default_settings()
    # WHEN save_settings is called
    save_settings(settings, config_file=config_file)
    # THEN juju_data_dir is still present
    data = yaml.safe_load(config_file.read_text())
    assert data["juju_data_dir"] == "/custom/path"


def test_save_settings_writes_log_level_as_name(tmp_path):
    # GIVEN settings with log_level=WARNING
    config_file = tmp_path / "config.yaml"
    settings = _default_settings(log_level=logging.WARNING)
    # WHEN save_settings is called
    save_settings(settings, config_file=config_file)
    # THEN log_level is written as the string "WARNING"
    data = yaml.safe_load(config_file.read_text())
    assert data["log_level"] == "WARNING"


def test_save_settings_creates_parent_dirs(tmp_path):
    # GIVEN a config path whose parent directories do not exist
    config_file = tmp_path / "nested" / "dir" / "config.yaml"
    settings = _default_settings()
    # WHEN save_settings is called
    save_settings(settings, config_file=config_file)
    # THEN the file is created (parent dirs are created automatically)
    assert config_file.exists()
