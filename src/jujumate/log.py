import logging
import logging.handlers
from pathlib import Path

from jujumate.settings import AppSettings


def setup_logging(settings: AppSettings) -> None:
    log_file: Path = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.addHandler(handler)
