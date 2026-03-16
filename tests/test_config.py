import pytest
import yaml

from jujumate.config import JujuConfig, JujuConfigError, load_config

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_controllers(tmp_path, data):
    (tmp_path / "controllers.yaml").write_text(yaml.dump(data))
    return tmp_path


def _write_models(tmp_path, data):
    (tmp_path / "models.yaml").write_text(yaml.dump(data))


_VALID_CONTROLLERS = {
    "controllers": {"prod": {}, "staging": {}},
    "current-controller": "prod",
}


# ── JujuConfig dataclass ──────────────────────────────────────────────────────


def test_juju_config_stores_fields():
    # GIVEN / WHEN
    config = JujuConfig(current_controller="prod", controllers=["prod", "staging"])

    # THEN
    assert config.current_controller == "prod"
    assert len(config.controllers) == 2


# ── load_config — happy path ──────────────────────────────────────────────────


def test_load_config_returns_current_controller(tmp_path):
    # GIVEN
    _write_controllers(tmp_path, _VALID_CONTROLLERS)

    # WHEN
    config = load_config(tmp_path)

    # THEN
    assert config.current_controller == "prod"


def test_load_config_returns_all_controllers(tmp_path):
    # GIVEN
    _write_controllers(tmp_path, _VALID_CONTROLLERS)

    # WHEN
    config = load_config(tmp_path)

    # THEN
    assert set(config.controllers) == {"prod", "staging"}


# ── load_config — current_model resolution ───────────────────────────────────


@pytest.mark.parametrize(
    "models_data,expected_current_model",
    [
        pytest.param(
            {"controllers": {"prod": {"current-model": "admin/mymodel"}}},
            "mymodel",
            id="model-with-owner-prefix",
        ),
        pytest.param(
            {"controllers": {"prod": {"current-model": "mymodel"}}},
            "mymodel",
            id="model-without-prefix",
        ),
        pytest.param(
            None,
            None,
            id="no-models-file",
        ),
    ],
)
def test_load_config_current_model(tmp_path, models_data, expected_current_model):
    # GIVEN
    _write_controllers(tmp_path, {"controllers": {"prod": {}}, "current-controller": "prod"})
    if models_data is not None:
        _write_models(tmp_path, models_data)

    # WHEN
    config = load_config(tmp_path)

    # THEN
    assert config.current_model == expected_current_model


# ── load_config — error conditions ───────────────────────────────────────────


@pytest.mark.parametrize(
    "yaml_data,expected_error_fragment",
    [
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
    ],
)
def test_load_config_raises_on_invalid_config(tmp_path, yaml_data, expected_error_fragment):
    # GIVEN
    if yaml_data is not None:
        _write_controllers(tmp_path, yaml_data)

    # WHEN / THEN
    with pytest.raises(JujuConfigError, match=expected_error_fragment):
        load_config(tmp_path)
