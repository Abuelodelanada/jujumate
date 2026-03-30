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
    assert config.controller_models == {}


def test_juju_config_default_controller_is_none():
    # GIVEN / WHEN
    config = JujuConfig()

    # THEN
    assert config.current_controller is None


# ── load_config — happy path ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "attribute, expected",
    [
        pytest.param("current_controller", "prod", id="current-controller"),
        pytest.param("controllers", {"prod", "staging"}, id="all-controllers"),
    ],
)
def test_load_config_basic_fields(tmp_path, attribute, expected):
    # GIVEN a valid controllers file
    _write_controllers(tmp_path, _VALID_CONTROLLERS)

    # WHEN load_config is called
    config = load_config(tmp_path)

    # THEN the requested field matches the expected value
    value = getattr(config, attribute)
    assert (set(value) if attribute == "controllers" else value) == expected


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


# ── load_config — controller_models ─────────────────────────────────────────


def test_load_config_builds_controller_models_for_all_controllers(tmp_path):
    # GIVEN: two controllers each with a current model
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}, "staging": {}}, "current-controller": "prod"},
    )
    _write_models(
        tmp_path,
        {
            "controllers": {
                "prod": {"current-model": "admin/mymodel"},
                "staging": {"current-model": "admin/stagingmodel"},
            }
        },
    )

    # WHEN
    config = load_config(tmp_path)

    # THEN
    assert config.controller_models == {"prod": "mymodel", "staging": "stagingmodel"}


def test_load_config_controller_models_excludes_controllers_without_model(tmp_path):
    # GIVEN: one controller has a current model, the other does not
    _write_controllers(
        tmp_path,
        {"controllers": {"prod": {}, "staging": {}}, "current-controller": "prod"},
    )
    _write_models(
        tmp_path,
        {"controllers": {"prod": {"current-model": "admin/mymodel"}}},
    )

    # WHEN
    config = load_config(tmp_path)

    # THEN
    assert "prod" in config.controller_models
    assert "staging" not in config.controller_models


# ── load_config — no default controller ──────────────────────────────────────


def test_load_config_no_current_controller_returns_none(tmp_path):
    # GIVEN: controllers file exists but no current-controller is set
    _write_controllers(
        tmp_path, {"controllers": {"prod": {}, "staging": {}}, "current-controller": ""}
    )

    # WHEN
    config = load_config(tmp_path)

    # THEN: does not raise; current_controller is None
    assert config.current_controller is None
    assert set(config.controllers) == {"prod", "staging"}
    assert config.current_model is None


# ── load_config — error conditions ───────────────────────────────────────────


@pytest.mark.parametrize(
    "yaml_data,expected_error_fragment",
    [
        pytest.param(None, "Juju config not found", id="missing-file"),
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
