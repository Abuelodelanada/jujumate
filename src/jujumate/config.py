import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_snap_real_home = os.environ.get("SNAP_REAL_HOME")
_real_home = Path(_snap_real_home) if _snap_real_home else Path.home()
JUJU_DATA_DIR = Path(os.environ.get("JUJU_DATA", _real_home / ".local" / "share" / "juju"))


@dataclass
class JujuConfig:
    current_controller: str | None = None
    controllers: list[str] = field(default_factory=list)
    current_model: str | None = None
    controller_models: dict[str, str] = field(default_factory=dict)


class JujuConfigError(Exception):
    pass


def load_config(juju_data_dir: Path = JUJU_DATA_DIR) -> JujuConfig:
    controllers_file = juju_data_dir / "controllers.yaml"

    if not controllers_file.exists():
        raise JujuConfigError(
            f"Juju config not found at {controllers_file}. Is Juju installed and configured?"
        )

    with controllers_file.open() as f:
        data = yaml.safe_load(f)

    controllers = list(data.get("controllers", {}).keys())
    current: str | None = data.get("current-controller") or None

    if current and current not in controllers:
        raise JujuConfigError(f"Current controller '{current}' not found in controllers list.")

    controller_models: dict[str, str] = {}
    models_file = juju_data_dir / "models.yaml"
    if models_file.exists():
        with models_file.open() as f:
            models_data = yaml.safe_load(f) or {}
        for ctrl_name in controllers:
            ctrl_data = (models_data.get("controllers") or {}).get(ctrl_name, {})
            raw = ctrl_data.get("current-model", "")
            if raw:
                # Strip user prefix (e.g. "admin/mymodel" → "mymodel")
                controller_models[ctrl_name] = raw.split("/", 1)[-1] if "/" in raw else raw

    current_model = controller_models.get(current) if current else None

    return JujuConfig(
        current_controller=current,
        controllers=controllers,
        current_model=current_model,
        controller_models=controller_models,
    )
