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


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(JujuConfigError, match="Juju config not found"):
        load_config(tmp_path)


def test_load_config_no_current_controller_raises(tmp_path):
    _write_controllers(
        tmp_path,
        {
            "controllers": {"prod": {}},
            "current-controller": "",
        },
    )
    with pytest.raises(JujuConfigError, match="No active controller"):
        load_config(tmp_path)


def test_load_config_current_not_in_list_raises(tmp_path):
    _write_controllers(
        tmp_path,
        {
            "controllers": {"prod": {}},
            "current-controller": "ghost",
        },
    )
    with pytest.raises(JujuConfigError, match="not found in controllers list"):
        load_config(tmp_path)


def test_juju_config_dataclass():
    config = JujuConfig(current_controller="prod", controllers=["prod", "staging"])
    assert config.current_controller == "prod"
    assert len(config.controllers) == 2


def _write_models(tmp_path, data):
    models_file = tmp_path / "models.yaml"
    models_file.write_text(yaml.dump(data))


def test_load_config_reads_current_model(tmp_path):
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}}, "current-controller": "prod"},
    )
    _write_models(
        tmp_path,
        {"controllers": {"prod": {"current-model": "admin/mymodel"}}},
    )
    config = load_config(tmp_path)
    assert config.current_model == "mymodel"


def test_load_config_current_model_without_prefix(tmp_path):
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}}, "current-controller": "prod"},
    )
    _write_models(
        tmp_path,
        {"controllers": {"prod": {"current-model": "mymodel"}}},
    )
    config = load_config(tmp_path)
    assert config.current_model == "mymodel"


def test_load_config_no_models_file_gives_none(tmp_path):
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}}, "current-controller": "prod"},
    )
    config = load_config(tmp_path)
    assert config.current_model is None
