import pytest
import yaml

from jujumate.config import JujuConfig, JujuConfigError, load_config


def _write_controllers(tmp_path, data):
    controllers_file = tmp_path / "controllers.yaml"
    controllers_file.write_text(yaml.dump(data))
    return tmp_path


def test_load_config_returns_current_controller(tmp_path):
    _write_controllers(
        tmp_path,
        {
            "controllers": {"prod": {}, "staging": {}},
            "current-controller": "prod",
        },
    )
    config = load_config(tmp_path)
    assert config.current_controller == "prod"


def test_load_config_returns_all_controllers(tmp_path):
    _write_controllers(
        tmp_path,
        {
            "controllers": {"prod": {}, "staging": {}},
            "current-controller": "prod",
        },
    )
    config = load_config(tmp_path)
    assert set(config.controllers) == {"prod", "staging"}


@pytest.mark.parametrize("yaml_data,expected_error_fragment", [
    pytest.param(None, "Juju config not found", id="missing-file"),
    pytest.param(
        {"controllers": {"prod": {}}, "current-controller": ""},
        "No active controller",
        id="no-current-controller",
    ),
    pytest.param(
        {"controllers": {"prod": {}}, "current-controller": "ghost"},
        "not found in controllers list",
        id="current-not-in-list",
    ),
])
def test_load_config_error_conditions(tmp_path, yaml_data, expected_error_fragment):
    if yaml_data is not None:
        _write_controllers(tmp_path, yaml_data)
    with pytest.raises(JujuConfigError, match=expected_error_fragment):
        load_config(tmp_path)


def test_juju_config_dataclass():
    config = JujuConfig(current_controller="prod", controllers=["prod", "staging"])
    assert config.current_controller == "prod"
    assert len(config.controllers) == 2


def _write_models(tmp_path, data):
    models_file = tmp_path / "models.yaml"
    models_file.write_text(yaml.dump(data))


@pytest.mark.parametrize("model_format,expected_current_model", [
    pytest.param("admin/mymodel", "mymodel", id="with-prefix"),
    pytest.param("mymodel", "mymodel", id="without-prefix"),
])
def test_load_config_current_model(tmp_path, model_format, expected_current_model):
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}}, "current-controller": "prod"},
    )
    _write_models(
        tmp_path,
        {"controllers": {"prod": {"current-model": model_format}}},
    )
    config = load_config(tmp_path)
    assert config.current_model == expected_current_model


def test_load_config_no_models_file_gives_none(tmp_path):
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}}, "current-controller": "prod"},
    )
    config = load_config(tmp_path)
    assert config.current_model is None
