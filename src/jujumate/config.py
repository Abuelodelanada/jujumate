from dataclasses import dataclass, field
from pathlib import Path

import yaml

JUJU_DATA_DIR = Path.home() / ".local" / "share" / "juju"


@dataclass
class JujuConfig:
    current_controller: str
    controllers: list[str] = field(default_factory=list)


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

    return JujuConfig(current_controller=current, controllers=controllers)
