from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    DataRefreshed,
    JujuPoller,
    ModelsUpdated,
    UnitsUpdated,
)
from jujumate.models.entities import AppInfo, CloudInfo, ModelInfo, UnitInfo


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_clouds.return_value = [CloudInfo("aws", "ec2")]
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
async def test_poll_once_posts_clouds(mock_client, mock_target):
    poller = JujuPoller(client=mock_client, target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert CloudsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_models(mock_client, mock_target):
    poller = JujuPoller(client=mock_client, target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ModelsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_apps_and_units(mock_client, mock_target):
    poller = JujuPoller(client=mock_client, target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert AppsUpdated in calls
    assert UnitsUpdated in calls


@pytest.mark.asyncio
async def test_poll_once_posts_data_refreshed(mock_client, mock_target):
    poller = JujuPoller(client=mock_client, target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert DataRefreshed in calls


@pytest.mark.asyncio
async def test_poll_once_posts_connection_failed_on_error(mock_target):
    client = AsyncMock()
    client.get_clouds.side_effect = Exception("timeout")
    poller = JujuPoller(client=client, target=mock_target)
    await poller.poll_once()
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls


def test_data_refreshed_has_timestamp():
    msg = DataRefreshed()
    assert isinstance(msg.timestamp, datetime)


def test_connection_failed_stores_error():
    msg = ConnectionFailed(error="timeout")
    assert msg.error == "timeout"
