import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

_snap_real_home = os.environ.get("SNAP_REAL_HOME")
_real_home = Path(_snap_real_home) if _snap_real_home else Path.home()

CONFIG_DIR = _real_home / ".config" / "jujumate"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass
class AppSettings:
    refresh_interval: int = 5
    offers_cache_ttl: int = 300
    default_controller: str | None = None
    juju_data_dir: Path = _real_home / ".local" / "share" / "juju"
    log_file: Path = _real_home / ".local" / "state" / "jujumate" / "jujumate.log"
    log_level: int = logging.INFO
    theme: str = "ubuntu"


class AppSettingsError(Exception):
    pass


def save_theme(theme_name: str, config_file: Path = CONFIG_FILE) -> None:
    """Persist the selected theme to the config file, preserving other settings."""
    data: dict = {}
    if config_file.exists():
        with config_file.open() as f:
            data = yaml.safe_load(f) or {}
    data["theme"] = theme_name
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def save_settings(settings: AppSettings, config_file: Path = CONFIG_FILE) -> None:
    """Persist all settings to the config file, preserving unmanaged keys."""
    data: dict = {}
    if config_file.exists():
        with config_file.open() as f:
            data = yaml.safe_load(f) or {}
    data["theme"] = settings.theme
    data["refresh_interval"] = settings.refresh_interval
    data["log_level"] = logging.getLevelName(settings.log_level)
    if settings.default_controller:
        data["default_controller"] = settings.default_controller
    else:
        data.pop("default_controller", None)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def load_settings(config_file: Path = CONFIG_FILE) -> AppSettings:
    if not config_file.exists():
        return AppSettings()

    with config_file.open() as f:
        data = yaml.safe_load(f) or {}

    refresh_interval = data.get("refresh_interval", AppSettings.refresh_interval)
    if not isinstance(refresh_interval, int) or refresh_interval < 1:
        raise AppSettingsError("'refresh_interval' must be an integer >= 1.")

    offers_cache_ttl = data.get("offers_cache_ttl", AppSettings.offers_cache_ttl)
    if not isinstance(offers_cache_ttl, int) or offers_cache_ttl < 1:
        raise AppSettingsError("'offers_cache_ttl' must be an integer >= 1.")

    juju_data_dir = (
        Path(data["juju_data_dir"]).expanduser()
        if "juju_data_dir" in data
        else AppSettings.juju_data_dir
    )

    log_file = Path(data["log_file"]).expanduser() if "log_file" in data else AppSettings.log_file

    log_level = AppSettings.log_level
    if "log_level" in data:
        level_str = str(data["log_level"]).upper()
        if level_str not in LOG_LEVELS:
            raise AppSettingsError(
                f"'log_level' must be one of {sorted(LOG_LEVELS)}, got '{level_str}'."
            )
        log_level = getattr(logging, level_str)

    return AppSettings(
        refresh_interval=refresh_interval,
        offers_cache_ttl=offers_cache_ttl,
        default_controller=data.get("default_controller"),
        juju_data_dir=juju_data_dir,
        log_file=log_file,
        log_level=log_level,
        theme=data.get("theme", AppSettings.theme),
    )
