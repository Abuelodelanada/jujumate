from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".config" / "jujumate"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


@dataclass
class AppSettings:
    refresh_interval: int = 5
    default_controller: str | None = None
    juju_data_dir: Path = Path.home() / ".local" / "share" / "juju"


class AppSettingsError(Exception):
    pass


def load_settings(config_file: Path = CONFIG_FILE) -> AppSettings:
    if not config_file.exists():
        return AppSettings()

    with config_file.open() as f:
        data = yaml.safe_load(f) or {}

    refresh_interval = data.get("refresh_interval", AppSettings.refresh_interval)
    if not isinstance(refresh_interval, int) or refresh_interval < 1:
        raise AppSettingsError("'refresh_interval' must be an integer >= 1.")

    juju_data_dir = (
        Path(data["juju_data_dir"]).expanduser()
        if "juju_data_dir" in data
        else AppSettings.juju_data_dir
    )

    return AppSettings(
        refresh_interval=refresh_interval,
        default_controller=data.get("default_controller"),
        juju_data_dir=juju_data_dir,
    )
