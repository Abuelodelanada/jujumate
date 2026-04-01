from contextlib import contextmanager
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
    OffersUpdated,
    RelationsUpdated,
    SaasUpdated,
    UnitsUpdated,
)
from jujumate.models.entities import (
    AppInfo,
    CloudInfo,
    ControllerInfo,
    MachineInfo,
    ModelInfo,
    OfferInfo,
    RelationInfo,
    UnitInfo,
)


def make_mock_client():
    """Return a mock JujuClient async context manager with realistic return values."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_clouds.return_value = [CloudInfo("aws", "ec2")]
    client.get_controllers.return_value = [ControllerInfo("prod", "aws", "", "3.4.0", 1)]
    client.list_model_names.return_value = ["dev"]
    client.get_model_snapshot.return_value = (
        ModelInfo("dev", "prod", "aws", "us-east-1", "available"),
        [AppInfo("postgresql", "dev", "postgresql", "14/stable", 363)],
        [UnitInfo("postgresql/0", "postgresql", "0", "active", "idle")],
        [MachineInfo("dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a")],
        [],  # relations
        [],  # offers
        [],  # saas
    )
    return client


@contextmanager
def _multi_clients_patch(*mock_clients):
    """Patch JujuClient to return the given mock clients in sequence."""
    clients = iter(mock_clients)
    with patch("jujumate.client.watcher.JujuClient", side_effect=lambda **_: next(clients)):
        yield


@pytest.fixture
def mock_target():
    target = MagicMock()
    target.post_message = MagicMock()
    return target


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_type",
    [
        pytest.param(CloudsUpdated, id="clouds"),
        pytest.param(ControllersUpdated, id="controllers"),
        pytest.param(ModelsUpdated, id="models"),
        pytest.param(AppsUpdated, id="apps"),
        pytest.param(UnitsUpdated, id="units"),
        pytest.param(RelationsUpdated, id="relations"),
        pytest.param(OffersUpdated, id="offers"),
        pytest.param(SaasUpdated, id="saas"),
        pytest.param(DataRefreshed, id="data_refreshed"),
    ],
)
async def test_poll_once_posts_expected_message_types(mock_target, expected_type):
    # GIVEN a poller connected to a mock client that returns realistic data
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)

        # WHEN poll_once is called
        await poller.poll_once()

    # THEN the expected message type is among the posted messages
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert expected_type in calls


@pytest.mark.asyncio
async def test_poll_once_posts_connection_failed_when_no_controllers(mock_target):
    # GIVEN a poller with an empty controller list
    poller = JujuPoller(controller_names=[], target=mock_target)

    # WHEN poll_once is called
    await poller.poll_once()

    # THEN a ConnectionFailed message is posted
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls


@pytest.mark.asyncio
async def test_poll_once_posts_connection_failed_when_all_controllers_fail(mock_target):
    # GIVEN a poller where all controllers raise an exception on connect
    failing_client = AsyncMock()
    failing_client.__aenter__ = AsyncMock(side_effect=Exception("refused"))
    failing_client.__aexit__ = AsyncMock(return_value=None)
    with patch("jujumate.client.watcher.JujuClient", return_value=failing_client):
        poller = JujuPoller(controller_names=["prod", "staging"], target=mock_target)

        # WHEN poll_once is called
        await poller.poll_once()

    # THEN a ConnectionFailed message is posted
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls


@pytest.mark.asyncio
async def test_poll_once_aggregates_multiple_controllers(mock_target):
    """Two controllers with distinct models → all models reported."""
    # GIVEN two controllers each with one distinct model
    client_a = make_mock_client()
    client_a.list_model_names.return_value = ["dev"]
    client_a.get_model_snapshot.return_value = (
        ModelInfo("dev", "ctrl-a", "aws", "", "available"),
        [],
        [],
        [],
        [],
        [],
        [],
    )
    client_b = make_mock_client()
    client_b.list_model_names.return_value = ["prod"]
    client_b.get_model_snapshot.return_value = (
        ModelInfo("prod", "ctrl-b", "aws", "", "available"),
        [],
        [],
        [],
        [],
        [],
        [],
    )

    with _multi_clients_patch(client_a, client_b):
        poller = JujuPoller(controller_names=["ctrl-a", "ctrl-b"], target=mock_target)

        # WHEN poll_once is called
        await poller.poll_once()

    # THEN the ModelsUpdated message contains both models
    models_msg = next(
        c.args[0]
        for c in mock_target.post_message.call_args_list
        if isinstance(c.args[0], ModelsUpdated)
    )
    assert len(models_msg.models) == 2


@pytest.mark.asyncio
async def test_poll_once_deduplicates_clouds(mock_target):
    """Two controllers sharing the same cloud → cloud appears only once."""
    # GIVEN two controllers that both report the same cloud
    client_a = make_mock_client()
    client_b = make_mock_client()  # also returns CloudInfo("aws", "ec2")

    with _multi_clients_patch(client_a, client_b):
        poller = JujuPoller(controller_names=["ctrl-a", "ctrl-b"], target=mock_target)

        # WHEN poll_once is called
        await poller.poll_once()

    # THEN CloudsUpdated contains only one cloud entry
    clouds_msg = next(
        c.args[0]
        for c in mock_target.post_message.call_args_list
        if isinstance(c.args[0], CloudsUpdated)
    )
    assert len(clouds_msg.clouds) == 1


@pytest.mark.asyncio
async def test_poll_once_calls_list_model_names_once_per_controller(mock_target):
    """list_model_names() is called exactly once; get_controllers() reuses the result."""
    # GIVEN a poller with a mock client
    client = make_mock_client()
    with patch("jujumate.client.watcher.JujuClient", return_value=client):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)

        # WHEN poll_once is called
        await poller.poll_once()

    # THEN list_model_names is called exactly once (not twice)
    client.list_model_names.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_once_polls_controllers_concurrently(mock_target):
    """poll_once() uses asyncio.gather so all controllers run in parallel."""
    import asyncio

    # GIVEN two controllers
    client_a = make_mock_client()
    client_b = make_mock_client()
    gather_calls: list[int] = []
    original_gather = asyncio.gather

    async def recording_gather(*coros, **kwargs):
        gather_calls.append(len(coros))
        return await original_gather(*coros, **kwargs)

    with _multi_clients_patch(client_a, client_b):
        with patch("jujumate.client.watcher.asyncio.gather", side_effect=recording_gather):
            poller = JujuPoller(controller_names=["ctrl-a", "ctrl-b"], target=mock_target)

            # WHEN poll_once is called
            await poller.poll_once()

    # THEN asyncio.gather was called with 2 coroutines (one per controller)
    assert gather_calls == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_type",
    [
        pytest.param(ModelsUpdated, id="models"),
        pytest.param(AppsUpdated, id="apps"),
        pytest.param(UnitsUpdated, id="units"),
        pytest.param(RelationsUpdated, id="relations"),
        pytest.param(OffersUpdated, id="offers"),
        pytest.param(SaasUpdated, id="saas"),
        pytest.param(DataRefreshed, id="data_refreshed"),
    ],
)
async def test_poll_model_posts_expected_message_types(mock_target, expected_type):
    # GIVEN a poller and a mock client that returns a full snapshot for one model
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)

        # WHEN poll_model is called with a specific controller and model
        await poller.poll_model("prod", "dev")

    # THEN the expected message type is among the posted messages
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert expected_type in calls


@pytest.mark.asyncio
async def test_poll_model_sets_controller_and_model_on_messages(mock_target):
    # GIVEN a poller and a mock client
    with patch("jujumate.client.watcher.JujuClient", return_value=make_mock_client()):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)

        # WHEN poll_model is called
        await poller.poll_model("prod", "dev")

    # THEN AppsUpdated carries the scoped controller and model fields
    apps_msg = next(
        c.args[0]
        for c in mock_target.post_message.call_args_list
        if isinstance(c.args[0], AppsUpdated)
    )
    assert apps_msg.controller == "prod"
    assert apps_msg.model == "dev"


@pytest.mark.asyncio
async def test_poll_model_posts_connection_failed_on_error(mock_target):
    # GIVEN a client that raises during get_model_snapshot
    failing_client = make_mock_client()
    failing_client.get_model_snapshot.side_effect = Exception("connection refused")
    with patch("jujumate.client.watcher.JujuClient", return_value=failing_client):
        poller = JujuPoller(controller_names=["prod"], target=mock_target)

        # WHEN poll_model is called
        await poller.poll_model("prod", "dev")

    # THEN a ConnectionFailed message is posted and no data messages are sent
    calls = [type(c.args[0]) for c in mock_target.post_message.call_args_list]
    assert ConnectionFailed in calls
    assert ModelsUpdated not in calls


def test_data_refreshed_has_timestamp():
    # GIVEN / WHEN a DataRefreshed message is instantiated
    msg = DataRefreshed()
    # THEN its timestamp is a datetime instance
    assert isinstance(msg.timestamp, datetime)


def test_connection_failed_stores_error():
    # GIVEN / WHEN a ConnectionFailed message is instantiated with an error string
    msg = ConnectionFailed(error="timeout")
    # THEN the error is stored correctly
    assert msg.error == "timeout"


def test_relations_updated_stores_model_and_relations():
    # GIVEN a RelationInfo and a RelationsUpdated message
    rel = RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular")
    # WHEN the message is instantiated
    msg = RelationsUpdated(model="dev", relations=[rel])
    # THEN the model and relations are stored correctly
    assert msg.model == "dev"
    assert len(msg.relations) == 1
    assert msg.relations[0].provider == "postgresql:db"


def test_offers_updated_stores_model_and_offers():
    # GIVEN an OfferInfo and an OffersUpdated message
    offer = OfferInfo(
        "cos",
        "alertmanager-karma-dashboard",
        "alertmanager",
        "alertmanager-k8s",
        180,
        "0/0",
        "karma-dashboard",
        "karma_dashboard",
        "provider",
    )
    # WHEN the message is instantiated
    msg = OffersUpdated(model="cos", offers=[offer])
    # THEN the model and offers are stored correctly
    assert msg.model == "cos"
    assert len(msg.offers) == 1
    assert msg.offers[0].name == "alertmanager-karma-dashboard"
