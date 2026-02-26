from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    ControllersUpdated,
    DataRefreshed,
    JujuPoller,
    ModelsUpdated,
    UnitsUpdated,
)
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo


def make_mock_client():
    """Return a mock JujuClient async context manager with realistic return values."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_clouds.return_value = [CloudInfo("aws", "ec2")]
    client.get_controllers.return_value = [ControllerInfo("prod", "aws", "", "3.4.0", 1)]
    client.get_models.return_value = [ModelInfo("dev", "prod", "aws", "us-east-1", "available")]
    client.get_applications.return_value = [
        AppInfo("postgresql", "dev", "postgresql", "14/stable", 363)
    ]
    client.get_units.return_value = [UnitInfo("postgresql/0", "postgresql", "0", "active", "idle")]
    return client


@pytest.fixture
def mock_target():
    target = MagicMock()
    target.post_message = MagicMock()
    return target


@pytest.mark.asyncio
async def test_poll_once_posts_clouds(mock_target):
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert CloudsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_controllers(mock_target):
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ControllersUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_models(mock_target):
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ModelsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_apps_and_units(mock_target):
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert AppsUpdated in calls
    assert UnitsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_data_refreshed(mock_target):
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert DataRefreshed in calls


@pytest.mark.asyncio
async def test_poll_once_posts_connection_failed_when_no_controllers(mock_target):
    poller = JujuPoller(controller_names=[], target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls


@pytest.mark.asyncio
async def test_poll_once_posts_connection_failed_when_all_controllers_fail(mock_target):
    failing_client = AsyncMock()
    failing_client.__aenter__ = AsyncMock(side_effect=Exception("refused"))
    failing_client.__aexit__ = AsyncMock(return_value=None)
    with patch("jujumate.client.watcher.JujuClient", return_value=failing_client):
        poller = JujuPoller(controller_names=["prod", "staging"], target=mock_target)
        await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls


@pytest.mark.asyncio
async def test_poll_once_aggregates_multiple_controllers(mock_target):
    """Two controllers with distinct models → all models reported."""
    client_a = make_mock_client()
    client_a.get_models.return_value = [ModelInfo("dev", "ctrl-a", "aws", "", "available")]
    client_b = make_mock_client()
    client_b.get_models.return_value = [ModelInfo("prod", "ctrl-b", "aws", "", "available")]

    clients = iter([client_a, client_b])
    with patch("jujumate.client.watcher.JujuClient", side_effect=lambda **_: next(clients)):
        poller = JujuPoller(controller_names=["ctrl-a", "ctrl-b"], target=mock_target)
        await poller.poll_once()

    models_msg = next(
        c.args[0]
        for c in mock_target.post_message.call_args_list
        if isinstance(c.args[0], ModelsUpdated)
    )
    assert len(models_msg.models) == 2


@pytest.mark.asyncio
async def test_poll_once_deduplicates_clouds(mock_target):
    """Two controllers sharing the same cloud → cloud appears only once."""
    client_a = make_mock_client()
    client_b = make_mock_client()  # also returns CloudInfo("aws", "ec2")

    clients = iter([client_a, client_b])
    with patch("jujumate.client.watcher.JujuClient", side_effect=lambda **_: next(clients)):
        poller = JujuPoller(controller_names=["ctrl-a", "ctrl-b"], target=mock_target)
        await poller.poll_once()

    clouds_msg = next(
        c.args[0]
        for c in mock_target.post_message.call_args_list
        if isinstance(c.args[0], CloudsUpdated)
    )
    assert len(clouds_msg.clouds) == 1


def test_data_refreshed_has_timestamp():
    msg = DataRefreshed()
    assert isinstance(msg.timestamp, datetime)


def test_connection_failed_stores_error():
    msg = ConnectionFailed(error="timeout")
    assert msg.error == "timeout"
