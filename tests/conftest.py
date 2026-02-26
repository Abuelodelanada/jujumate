"""
Pytest configuration and shared fixtures.

The ``no_juju_connection`` fixture prevents tests from accidentally connecting
to a real Juju controller by patching ``load_config`` to raise
``JujuConfigError``.  It is applied automatically to every test so the test
suite can run safely on machines that have Juju installed.
"""

from unittest.mock import patch

import pytest

from jujumate.config import JujuConfigError


@pytest.fixture(autouse=True)
def no_juju_connection():
    """Prevent accidental connections to real Juju controllers during tests."""
    with patch(
        "jujumate.screens.main_screen.load_config",
        side_effect=JujuConfigError("Juju not available in test environment"),
    ):
        yield
