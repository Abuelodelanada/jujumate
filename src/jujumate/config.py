from dataclasses import dataclass, field
from pathlib import Path

import yaml

JUJU_DATA_DIR = Path.home() / ".local" / "share" / "juju"


@dataclass
class JujuConfig:
    current_controller: str
    controllers: list[str] = field(default_factory=list)
    current_model: str | None = None


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
    current = data.get("current-controller", "")

    if not current:
        raise JujuConfigError("No active controller found in Juju config.")

    if current not in controllers:
        raise JujuConfigError(f"Current controller '{current}' not found in controllers list.")

    current_model: str | None = None
    models_file = juju_data_dir / "models.yaml"
    if models_file.exists():
        with models_file.open() as f:
            models_data = yaml.safe_load(f) or {}
        ctrl_data = (models_data.get("controllers") or {}).get(current, {})
        raw = ctrl_data.get("current-model", "")
        if raw:
            # Strip user prefix (e.g. "admin/mymodel" → "mymodel")
            current_model = raw.split("/", 1)[-1] if "/" in raw else raw

    return JujuConfig(current_controller=current, controllers=controllers, current_model=current_model)
