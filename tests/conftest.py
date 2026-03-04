"""
Pytest configuration and shared fixtures.

The ``no_juju_connection`` fixture prevents tests from accidentally connecting
to a real Juju controller by patching ``load_config`` to raise
``JujuConfigError``.  It is applied automatically to every test so the test
suite can run safely on machines that have Juju installed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from jujumate.app import JujuMateApp
from jujumate.config import JujuConfigError
from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    RelationDataEntry,
    RelationInfo,
    SecretInfo,
    UnitInfo,
)


@pytest.fixture(autouse=True)
def no_juju_connection():
    """Prevent accidental connections to real Juju controllers during tests."""
    with patch(
        "jujumate.screens.main_screen.load_config",
        side_effect=JujuConfigError("Juju not available in test environment"),
    ):
        yield


# ─────────────────────────────────────────────────────────────────────────────
# Textual pilot
# ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def pilot():
    """Shared Textual Pilot. Use ``pilot.app`` to access the JujuMateApp instance."""
    app = JujuMateApp()
    async with app.run_test() as p:
        await p.pause()
        yield p


# ─────────────────────────────────────────────────────────────────────────────
# Entity fixtures (sensible defaults; override fields in-test as needed)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_pg() -> AppInfo:
    return AppInfo("pg", "dev", "postgresql", "14/stable", 1, status="active")


@pytest.fixture
def unit_pg0() -> UnitInfo:
    return UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1")


@pytest.fixture
def relation_pg_wp() -> RelationInfo:
    return RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)


@pytest.fixture
def secret_one() -> SecretInfo:
    return SecretInfo(
        uri="csec:abc123",
        label="my-secret",
        owner="dev",
        description="A test secret",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )


@pytest.fixture
def config_entries() -> list[AppConfigEntry]:
    return [
        AppConfigEntry("log-level", "DEBUG", "INFO", "string", "Log level", "user"),
        AppConfigEntry("port", "5432", "5432", "int", "Port", "default"),
    ]


@pytest.fixture
def relation_data_entries() -> list[RelationDataEntry]:
    return [
        RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app"),
        RelationDataEntry("provider", "pg/0", "port", "5432", "unit"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Juju controller mock (for test_juju_client.py)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_controller():
    with patch("jujumate.client.juju_client.Controller") as MockController:
        ctrl = AsyncMock()
        ctrl.controller_name = "test-controller"
        MockController.return_value = ctrl
        yield ctrl
