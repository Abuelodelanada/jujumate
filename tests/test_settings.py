import logging

import pytest
import yaml

from jujumate.settings import AppSettingsError, load_settings, save_theme


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


def test_empty_file_returns_defaults(tmp_path):
    # GIVEN a config file that exists but is empty
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    # WHEN load_settings is called
    settings = load_settings(config_file)
    # THEN default values are returned
    assert settings.refresh_interval == 5


def test_default_log_level_is_warning(tmp_path):
    # GIVEN no config file at the given path
    # WHEN load_settings is called
    settings = load_settings(tmp_path / "config.yaml")
    # THEN the default log level is INFO
    assert settings.log_level == logging.INFO


def test_custom_log_level(tmp_path):
    # GIVEN a config file specifying DEBUG as the log level
    config_file = _write_config(tmp_path, {"log_level": "DEBUG"})
    # WHEN load_settings is called
    settings = load_settings(config_file)
    # THEN the log level is set to DEBUG
    assert settings.log_level == logging.DEBUG


def test_log_level_case_insensitive(tmp_path):
    # GIVEN a config file specifying the log level in lowercase
    config_file = _write_config(tmp_path, {"log_level": "info"})
    # WHEN load_settings is called
    settings = load_settings(config_file)
    # THEN the log level is correctly resolved
    assert settings.log_level == logging.INFO


def test_invalid_log_level_raises(tmp_path):
    # GIVEN a config file with an unrecognised log level
    config_file = _write_config(tmp_path, {"log_level": "VERBOSE"})
    # WHEN load_settings is called
    # THEN an AppSettingsError is raised mentioning log_level
    with pytest.raises(AppSettingsError, match="log_level"):
        load_settings(config_file)


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
