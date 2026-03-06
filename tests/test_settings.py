import logging

import pytest
import yaml

from jujumate.settings import AppSettingsError, load_settings


def _write_config(tmp_path, data):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


def test_defaults_when_file_missing(tmp_path):
    settings = load_settings(tmp_path / "config.yaml")
    assert settings.refresh_interval == 5
    assert settings.default_controller is None


def test_custom_refresh_interval(tmp_path):
    config_file = _write_config(tmp_path, {"refresh_interval": 10})
    settings = load_settings(config_file)
    assert settings.refresh_interval == 10


def test_custom_default_controller(tmp_path):
    config_file = _write_config(tmp_path, {"default_controller": "prod"})
    settings = load_settings(config_file)
    assert settings.default_controller == "prod"


def test_custom_juju_data_dir(tmp_path):
    config_file = _write_config(tmp_path, {"juju_data_dir": str(tmp_path)})
    settings = load_settings(config_file)
    assert settings.juju_data_dir == tmp_path


def test_invalid_refresh_interval_raises(tmp_path):
    config_file = _write_config(tmp_path, {"refresh_interval": 0})
    with pytest.raises(AppSettingsError, match="refresh_interval"):
        load_settings(config_file)


def test_non_integer_refresh_interval_raises(tmp_path):
    config_file = _write_config(tmp_path, {"refresh_interval": "fast"})
    with pytest.raises(AppSettingsError, match="refresh_interval"):
        load_settings(config_file)


def test_empty_file_returns_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    settings = load_settings(config_file)
    assert settings.refresh_interval == 5


def test_default_log_level_is_warning(tmp_path):
    settings = load_settings(tmp_path / "config.yaml")
    assert settings.log_level == logging.INFO


def test_custom_log_level(tmp_path):
    config_file = _write_config(tmp_path, {"log_level": "DEBUG"})
    settings = load_settings(config_file)
    assert settings.log_level == logging.DEBUG


def test_log_level_case_insensitive(tmp_path):
    config_file = _write_config(tmp_path, {"log_level": "info"})
    settings = load_settings(config_file)
    assert settings.log_level == logging.INFO


def test_invalid_log_level_raises(tmp_path):
    config_file = _write_config(tmp_path, {"log_level": "VERBOSE"})
    with pytest.raises(AppSettingsError, match="log_level"):
        load_settings(config_file)


def test_custom_log_file(tmp_path):
    config_file = _write_config(tmp_path, {"log_file": str(tmp_path / "app.log")})
    settings = load_settings(config_file)
    assert settings.log_file == tmp_path / "app.log"
