import logging

from jujumate.log import setup_logging
from jujumate.settings import AppSettings


def test_setup_logging_creates_log_file(tmp_path):
    # GIVEN settings that specify a log file in a directory that does not yet exist
    settings = AppSettings(log_file=tmp_path / "logs" / "jujumate.log")

    # WHEN setup_logging is called
    setup_logging(settings)

    # THEN the parent directory is created automatically
    assert (tmp_path / "logs").exists()


def test_setup_logging_sets_log_level(tmp_path):
    # GIVEN settings that specify DEBUG as the log level
    settings = AppSettings(log_file=tmp_path / "jujumate.log", log_level=logging.DEBUG)

    # WHEN setup_logging is called
    setup_logging(settings)

    # THEN the root logger is configured at DEBUG level
    assert logging.getLogger().level == logging.DEBUG
