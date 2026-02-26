import logging

from jujumate.log import setup_logging
from jujumate.settings import AppSettings


def test_setup_logging_creates_log_file(tmp_path):
    settings = AppSettings(log_file=tmp_path / "logs" / "jujumate.log")
    setup_logging(settings)
    assert (tmp_path / "logs").exists()


def test_setup_logging_sets_log_level(tmp_path):
    settings = AppSettings(log_file=tmp_path / "jujumate.log", log_level=logging.DEBUG)
    setup_logging(settings)
    assert logging.getLogger().level == logging.DEBUG
