import asyncio
import base64
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets
import websockets.exceptions
from juju.errors import JujuConnectionError, JujuError

from jujumate.client.juju_client import (
    JujuClient,
    JujuClientError,
    _build_log_stream_url,
    _build_ssl_context,
    _decode_secret_value,
    _log_stream_connection_params,
    _offer_status_counts,
    _parse_app_relation_data,
    _parse_hw,
    _parse_log_entry,
    _parse_machine_info,
    _parse_relation,
    _parse_unit_relation_data,
    _resolve_model_uuid,
    _s,
    _since_to_iso,
    _utc_ts_to_local_hms,
)
from jujumate.models.entities import (
    AppConfigEntry,
    ControllerOfferInfo,
    RelationDataEntry,
    SecretInfo,
)


def _make_model_mock(
    app_name="postgresql",
    charm_name="postgresql",
    channel="14/stable",
    revision=363,
    unit_name="postgresql/0",
    unit_address="10.0.0.1",
    is_kubernetes=False,
):
    """Build a model mock that works with get_model_snapshot (uses get_status)."""
    app_st = MagicMock()
    app_st.charm_channel = channel
    app_st.charm_rev = revision
    app_st.workload_version = "1.0.0"
    app_st.public_address = "10.0.0.5"
    app_st.exposed = False
    app_st.status.status = "active"
    app_st.status.info = ""
    unit_st = MagicMock()
    unit_st.machine = "" if is_kubernetes else "0"
    unit_st.workload_status.status = "active"
    unit_st.workload_status.info = "ready"
    unit_st.agent_status.status = "idle"
    unit_st.public_address = "" if is_kubernetes else unit_address
    unit_st.address = unit_address if is_kubernetes else ""
    unit_st.opened_ports = ["5432/tcp"]
    app_st.units = {unit_name: unit_st}
    machine_mock = MagicMock()
    machine_mock.agent_status.status = "started"
    machine_mock.dns_name = "10.0.0.1"
    machine_mock.instance_id = "i-1234"
    machine_mock.base.name = "ubuntu"
    machine_mock.base.channel = "22.04"
    machine_mock.hardware = "arch=amd64 cores=2 mem=8192M availability-zone=us-east-1a"
    machine_mock.instance_status.info = "running"
    full_status = MagicMock()
    full_status.applications = {app_name: app_st}
    full_status.machines = {} if is_kubernetes else {"0": machine_mock}
    full_status.relations = []
    info = MagicMock()
    info.cloud_tag = "cloud-aws"
    info.cloud_region = "us-east-1"
    info.status.status = "active"
    info.type_ = "caas" if is_kubernetes else "iaas"
    live_app = MagicMock()
    live_app.charm_name = charm_name
    model = AsyncMock()
    model.info = info
    model.applications = {app_name: live_app}
    model.get_status = AsyncMock(return_value=full_status)
    return model, app_st, unit_st


def _make_stream_logs_controller(mock_controller) -> None:
    """Configure mock_controller with connection params for stream_logs tests."""
    mock_controller.model_uuids = AsyncMock(return_value={"dev": "uuid-123"})
    conn = MagicMock()
    conn.connect_params.return_value = {
        "endpoint": "10.0.0.1:17070",
        "password": "secret",
        "cacert": None,
    }
    conn.username = "admin"
    mock_controller.connection = MagicMock(return_value=conn)


def _make_relation_model(mock_controller: MagicMock, apps_units: dict) -> AsyncMock:
    """Build a model mock for get_relation_data tests.

    apps_units: {"app_name": [unit_mock, ...]}  — pass [] for apps with no units.
    """
    model = AsyncMock()
    model.connection = MagicMock(return_value=MagicMock())
    model.applications = {name: MagicMock(units=units) for name, units in apps_units.items()}
    mock_controller.get_model = AsyncMock(return_value=model)
    return model


def _make_status_mock(**overrides) -> MagicMock:
    """Build a minimal FullStatus mock with sensible defaults."""
    status = MagicMock()
    status.relations = overrides.get("relations", [])
    status.applications = overrides.get("applications", {})
    status.offers = overrides.get("offers", {})
    status.remote_applications = overrides.get("remote_applications", {})
    status.application_endpoints = overrides.get("application_endpoints", {})
    status.unknown_fields = overrides.get("unknown_fields", {})
    return status


def _make_status_with_relation(mock_controller: MagicMock, *rels: MagicMock) -> None:
    """Configure mock_controller with a model that returns a status containing *rels."""
    model = AsyncMock()
    status = _make_status_mock(relations=list(rels))
    model.get_status = AsyncMock(return_value=status)
    model.applications = {}
    mock_controller.get_model.return_value = model


@pytest.mark.asyncio
async def test_connect_current(mock_controller):
    # GIVEN a client with no controller name (connects to current)
    # WHEN connect() is called
    client = JujuClient(controller=mock_controller)
    await client.connect()
    # THEN connect_current is called once
    mock_controller.connect_current.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_named_controller(mock_controller):
    # GIVEN a client configured with a specific controller name
    # WHEN connect() is called
    client = JujuClient(controller_name="prod", controller=mock_controller)
    await client.connect()
    # THEN connect is called with that name
    mock_controller.connect.assert_awaited_once_with("prod")


@pytest.mark.asyncio
async def test_connect_raises_on_failure(mock_controller):
    # GIVEN a controller that raises JujuConnectionError
    mock_controller.connect_current.side_effect = JujuConnectionError("connection refused")
    # WHEN connect() is called
    client = JujuClient(controller=mock_controller)
    # THEN JujuClientError is raised with a descriptive message
    with pytest.raises(JujuClientError, match="Failed to connect"):
        await client.connect()


@pytest.mark.asyncio
async def test_context_manager_connects_and_disconnects(mock_controller):
    # GIVEN a JujuClient used as async context manager
    # WHEN the block is entered and exited
    async with JujuClient(controller=mock_controller):
        # THEN connect_current was called on enter
        mock_controller.connect_current.assert_awaited_once()
    # THEN disconnect is called on exit
    mock_controller.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_clouds(mock_controller):
    # GIVEN a controller that returns one cloud with a region
    region = MagicMock()
    region.name = "us-east-1"
    cloud = MagicMock()
    cloud.type_ = "ec2"
    cloud.regions = [region]
    mock_controller.clouds.return_value = MagicMock(clouds={"cloud-aws": cloud})
    # WHEN get_clouds is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_clouds()
    # THEN cloud name is stripped of "cloud-" prefix and fields are correct
    assert len(result) == 1
    assert result[0].name == "aws"
    assert result[0].type == "ec2"
    assert result[0].regions == ["us-east-1"]


@pytest.mark.asyncio
async def test_get_models(mock_controller):
    # GIVEN a controller with two models
    mock_controller.list_models.return_value = ["dev", "prod"]
    model, _, _ = _make_model_mock()
    mock_controller.get_model.return_value = model
    # WHEN get_models is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_models()
    # THEN both models are returned with correct info
    assert len(result) == 2
    assert result[0].name == "dev"
    assert result[0].cloud == "aws"
    assert result[0].app_count == 1


@pytest.mark.asyncio
async def test_list_model_names(mock_controller):
    # GIVEN a controller that returns model names
    mock_controller.list_models.return_value = ["dev", "prod"]
    # WHEN list_model_names is called
    client = JujuClient(controller=mock_controller)
    result = await client.list_model_names()
    # THEN the raw list is returned as-is
    assert result == ["dev", "prod"]


@pytest.mark.asyncio
async def test_get_model_snapshot(mock_controller):
    # GIVEN an IaaS model with one app, one unit and one machine
    model, app_st, unit_st = _make_model_mock()
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    model_info, apps, units, machines = await client.get_model_snapshot("dev")
    # THEN all parsed fields are correct and only one get_model call was made
    assert model_info.name == "dev"
    assert model_info.cloud == "aws"
    assert model_info.status == "active"
    assert model_info.machine_count == 1
    assert model_info.is_kubernetes is False
    assert len(apps) == 1
    assert apps[0].name == "postgresql"
    assert apps[0].channel == "14/stable"
    assert apps[0].revision == 363
    assert apps[0].address == "10.0.0.5"
    assert apps[0].exposed is False
    assert len(units) == 1
    assert units[0].name == "postgresql/0"
    assert units[0].machine == "0"
    assert units[0].public_address == "10.0.0.1"
    assert units[0].address == ""
    assert units[0].ports == "5432/tcp"
    assert units[0].message == "ready"
    assert len(machines) == 1
    assert machines[0].model == "dev"
    assert machines[0].id == "0"
    assert machines[0].state == "started"
    assert machines[0].address == "10.0.0.1"
    assert machines[0].instance_id == "i-1234"
    assert machines[0].base == "ubuntu@22.04"
    assert machines[0].az == "us-east-1a"
    assert machines[0].message == "running"
    # Only ONE get_model call for all data
    mock_controller.get_model.assert_awaited_once_with("dev")


@pytest.mark.asyncio
async def test_get_model_snapshot_kubernetes(mock_controller):
    # GIVEN a Kubernetes (caas) model
    model, _, _ = _make_model_mock(is_kubernetes=True, unit_address="10.1.2.3")
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    model_info, apps, units, machines = await client.get_model_snapshot("cos")
    # THEN is_kubernetes is True, machines empty, and unit uses address (not public_address)
    assert model_info.is_kubernetes is True
    assert model_info.machine_count == 0
    assert units[0].machine == ""
    assert units[0].address == "10.1.2.3"
    assert units[0].public_address == ""
    assert machines == []


@pytest.mark.asyncio
async def test_get_model_snapshot_fallback_on_failure(mock_controller):
    # GIVEN a model that raises JujuError on get_model
    mock_controller.get_model.side_effect = JujuError("timeout")
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    model_info, apps, units, machines = await client.get_model_snapshot("broken")
    # THEN a minimal fallback ModelInfo is returned with empty lists
    assert model_info.status == "unknown"
    assert apps == []
    assert units == []
    assert machines == []


@pytest.mark.asyncio
async def test_get_model_snapshot_includes_subordinate_units(mock_controller):
    # GIVEN a model with a unit that has a subordinate
    model, app_st, unit_st = _make_model_mock()
    sub_st = MagicMock()
    sub_st.workload_status.status = "active"
    sub_st.workload_status.info = "Unit is ready"
    sub_st.agent_status.status = "idle"
    sub_st.address = ""
    sub_st.public_address = "10.0.0.1"
    sub_st.opened_ports = []
    unit_st.subordinates = {"nrpe/0": sub_st}
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, _, units, _ = await client.get_model_snapshot("dev")
    # THEN both the principal unit and the subordinate are returned
    assert len(units) == 2
    sub = next(u for u in units if u.name == "nrpe/0")
    assert sub.app == "nrpe"
    assert sub.subordinate_of == "postgresql/0"
    assert sub.machine == "0"
    assert sub.message == "Unit is ready"


@pytest.mark.asyncio
async def test_get_model_snapshot_subordinate_leader_flag_set(mock_controller):
    # GIVEN a model with a subordinate unit that is a leader
    model, app_st, unit_st = _make_model_mock()
    sub_st = MagicMock()
    sub_st.workload_status.status = "active"
    sub_st.workload_status.info = ""
    sub_st.agent_status.status = "idle"
    sub_st.address = ""
    sub_st.public_address = "10.0.0.1"
    sub_st.opened_ports = []
    sub_st.leader = True
    unit_st.subordinates = {"nrpe/0": sub_st}
    mock_controller.get_model.return_value = model

    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, _, units, _ = await client.get_model_snapshot("dev")

    # THEN the subordinate unit has is_leader=True
    sub = next(u for u in units if u.name == "nrpe/0")
    assert sub.is_leader is True


@pytest.mark.asyncio
async def test_get_model_snapshot_subordinate_non_leader_flag_false(mock_controller):
    # GIVEN a model with a subordinate unit that is NOT a leader
    model, app_st, unit_st = _make_model_mock()
    sub_st = MagicMock()
    sub_st.workload_status.status = "active"
    sub_st.workload_status.info = ""
    sub_st.agent_status.status = "idle"
    sub_st.address = ""
    sub_st.public_address = "10.0.0.1"
    sub_st.opened_ports = []
    sub_st.leader = False
    unit_st.subordinates = {"nrpe/0": sub_st}
    mock_controller.get_model.return_value = model

    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, _, units, _ = await client.get_model_snapshot("dev")

    # THEN the subordinate unit has is_leader=False
    sub = next(u for u in units if u.name == "nrpe/0")
    assert sub.is_leader is False


@pytest.mark.asyncio
async def test_get_applications(mock_controller):
    # GIVEN a model with one application
    model, _, _ = _make_model_mock()
    mock_controller.get_model.return_value = model
    # WHEN get_applications is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_applications("dev")
    # THEN the application list is correct
    assert len(result) == 1
    assert result[0].name == "postgresql"
    assert result[0].channel == "14/stable"
    assert result[0].revision == 363
    assert result[0].unit_count == 1


@pytest.mark.asyncio
async def test_get_units(mock_controller):
    # GIVEN a model with one unit
    model, _, _ = _make_model_mock(unit_address="10.0.0.1")
    mock_controller.get_model.return_value = model
    # WHEN get_units is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_units("dev")

    # THEN the unit list is correct
    assert len(result) == 1
    assert result[0].name == "postgresql/0"
    assert result[0].public_address == "10.0.0.1"
    assert result[0].ports == "5432/tcp"
    assert result[0].message == "ready"


@pytest.mark.asyncio
async def test_get_models_falls_back_on_failed_model(mock_controller):
    # GIVEN two models where the first raises JujuError
    mock_controller.list_models.return_value = ["broken", "ok"]
    ok_model, _, _ = _make_model_mock()
    mock_controller.get_model.side_effect = [JujuError("boom"), ok_model]
    # WHEN get_models is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_models()
    # THEN both models are returned: broken with fallback status, ok with full info
    assert len(result) == 2
    broken = next(m for m in result if m.name == "broken")
    assert broken.status == "unknown"
    assert broken.cloud == ""
    ok = next(m for m in result if m.name == "ok")
    assert ok.cloud == "aws"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    [
        pytest.param("get_applications", id="get_applications"),
        pytest.param("get_units", id="get_units"),
    ],
)
async def test_get_returns_empty_on_failure(mock_controller, method_name):
    # GIVEN a model that raises JujuError
    mock_controller.get_model.side_effect = JujuError("boom")
    # WHEN get_applications or get_units is called
    client = JujuClient(controller=mock_controller)
    result = await getattr(client, method_name)("broken-model")
    # THEN an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_controllers(mock_controller):
    # GIVEN a controller with version info and two models
    conn = MagicMock()
    conn.info = {"server-version": "3.4.0"}
    mock_controller.connection = MagicMock(return_value=conn)
    mock_controller.get_cloud = AsyncMock(return_value="aws")
    mock_controller.list_models = AsyncMock(return_value=["dev", "prod"])
    # WHEN get_controllers is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_controllers()
    # THEN controller info is correctly parsed
    assert len(result) == 1
    assert result[0].name == "test-controller"
    assert result[0].cloud == "aws"
    assert result[0].juju_version == "3.4.0"
    assert result[0].model_count == 2


@pytest.mark.asyncio
async def test_get_controllers_returns_empty_on_failure(mock_controller):
    # GIVEN a controller where get_cloud raises JujuError
    mock_controller.get_cloud.side_effect = JujuError("boom")
    # WHEN get_controllers is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_controllers()
    # THEN an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_relations(mock_controller):
    # GIVEN a model with a regular provider/requirer relation
    rel = MagicMock()
    rel.interface = "pgsql"
    rel.id_ = 0
    provider_ep = MagicMock()
    provider_ep.application = "postgresql"
    provider_ep.name = "db"
    provider_ep.role = "provider"
    requirer_ep = MagicMock()
    requirer_ep.application = "wordpress"
    requirer_ep.name = "db"
    requirer_ep.role = "requirer"
    rel.endpoints = [provider_ep, requirer_ep]
    _make_status_with_relation(mock_controller, rel)
    # WHEN get_relations is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_relations("dev")
    # THEN the relation is parsed with correct provider/requirer
    assert len(result) == 1
    assert result[0].provider == "postgresql:db"
    assert result[0].requirer == "wordpress:db"
    assert result[0].interface == "pgsql"
    assert result[0].type == "regular"
    assert result[0].model == "dev"


@pytest.mark.asyncio
async def test_get_relations_peer(mock_controller):
    # GIVEN a model with a peer relation
    rel = MagicMock()
    rel.interface = "etcd"
    peer_ep = MagicMock()
    peer_ep.application = "etcd"
    peer_ep.name = "cluster"
    peer_ep.role = "peer"
    rel.endpoints = [peer_ep]
    _make_status_with_relation(mock_controller, rel)
    # WHEN get_relations is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_relations("dev")
    # THEN the peer relation is parsed correctly
    assert len(result) == 1
    assert result[0].provider == "etcd:cluster"
    assert result[0].requirer == "etcd:cluster"
    assert result[0].type == "peer"


@pytest.mark.asyncio
async def test_get_relations_raises_on_failure(mock_controller):
    # GIVEN a model that raises a generic Exception
    mock_controller.get_model.side_effect = Exception("boom")
    # WHEN get_relations is called
    client = JujuClient(controller=mock_controller)
    # THEN the exception propagates
    with pytest.raises(Exception, match="boom"):
        await client.get_relations("broken-model")


@pytest.mark.asyncio
async def test_get_status_details_returns_offers(mock_controller):
    # GIVEN a model with one offer and no relations
    app_st = MagicMock()
    app_st.charm_rev = 180
    offer_st = MagicMock()
    offer_st.application_name = "alertmanager"
    offer_st.active_connected_count = 0
    offer_st.total_connected_count = 0
    ep = MagicMock()
    ep.interface = "karma_dashboard"
    ep.role = "provider"
    offer_st.endpoints = {"karma-dashboard": ep}
    status = _make_status_mock(
        applications={"alertmanager": app_st},
        offers={"alertmanager-karma-dashboard": offer_st},
    )
    live_app = MagicMock()
    live_app.charm_name = "alertmanager-k8s"
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    model.applications = {"alertmanager": live_app}
    mock_controller.get_model.return_value = model
    # WHEN get_status_details is called
    client = JujuClient(controller=mock_controller)
    relations, offers, saas = await client.get_status_details("cos")
    # THEN the offer is parsed with all fields correct
    assert relations == []
    assert len(offers) == 1
    o = offers[0]
    assert o.name == "alertmanager-karma-dashboard"
    assert o.application == "alertmanager"
    assert o.charm == "alertmanager-k8s"
    assert o.rev == 180
    assert o.connected == "0/0"
    assert o.endpoint == "karma-dashboard"
    assert o.interface == "karma_dashboard"
    assert o.role == "provider"


# ─────────────────────────────────────────────────────────────────────────────
# get_secrets
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner_tag,expected_owner",
    [
        pytest.param("model-dev", "dev", id="with-dash"),
        pytest.param("modelonly", "modelonly", id="without-dash"),
    ],
)
async def test_get_secrets_owner_tag_parsing(mock_controller, owner_tag, expected_owner):
    # GIVEN a secret whose owner_tag may or may not contain a dash prefix
    model = AsyncMock()
    model.name = "dev"
    mock_secret = MagicMock()
    mock_secret.uri = "csec:abc123"
    mock_secret.label = "my-secret"
    mock_secret.owner_tag = owner_tag
    mock_secret.latest_revision = 2
    mock_secret.create_time = "2024-01-01T00:00:00"
    model.list_secrets = AsyncMock(return_value=[mock_secret])
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_secrets is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_secrets("dev")
    # THEN the owner is stripped of the prefix when present
    assert len(result) == 1
    assert isinstance(result[0], SecretInfo)
    assert result[0].owner == expected_owner


@pytest.mark.asyncio
async def test_get_secrets_empty(mock_controller):
    # GIVEN a model with no secrets
    model = AsyncMock()
    model.name = "dev"
    model.list_secrets = AsyncMock(return_value=[])
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_secrets is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_secrets("dev")
    # THEN an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_secrets_raises_juju_error_when_model_gone(mock_controller):
    # GIVEN the controller raises InvalidStatusCode (model was removed)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_secrets is called for the removed model
    # THEN a JujuError is raised instead of crashing
    with pytest.raises(JujuError, match="no longer available"):
        await client.get_secrets("removed-model")


# ─────────────────────────────────────────────────────────────────────────────
# get_app_config
# ─────────────────────────────────────────────────────────────────────────────


def _make_app_config_model(mock_controller: MagicMock, config: dict) -> None:
    """Configure mock_controller with a model whose 'pg' app returns *config*."""
    model = AsyncMock()
    app_obj = AsyncMock()
    app_obj.get_config = AsyncMock(return_value=config)
    model.applications = {"pg": app_obj}
    mock_controller.get_model = AsyncMock(return_value=model)


@pytest.mark.asyncio
async def test_get_app_config(mock_controller):
    # GIVEN an app with two config entries (one user-set, one default)
    _make_app_config_model(
        mock_controller,
        {
            "log-level": {
                "value": "DEBUG",
                "default": "INFO",
                "type": "string",
                "description": "Level",
                "source": "user",
            },
            "port": {
                "value": 5432,
                "default": 5432,
                "type": "int",
                "description": "Port",
                "source": "default",
            },
        },
    )
    # WHEN get_app_config is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_app_config("dev", "pg")
    # THEN both entries are returned as AppConfigEntry objects
    assert len(result) == 2
    assert all(isinstance(e, AppConfigEntry) for e in result)
    keys = {e.key for e in result}
    assert keys == {"log-level", "port"}


@pytest.mark.asyncio
async def test_get_app_config_non_dict_values_skipped(mock_controller):
    # GIVEN a config where one entry is not a dict
    _make_app_config_model(
        mock_controller,
        {
            "good": {
                "value": "v",
                "default": "d",
                "type": "string",
                "description": "desc",
                "source": "user",
            },
            "bad": "not-a-dict",
        },
    )
    # WHEN get_app_config is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_app_config("dev", "pg")
    # THEN only the dict entry is returned
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_app_config_app_not_found(mock_controller):
    # GIVEN a model with no applications
    model = AsyncMock()
    model.applications = {}
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_app_config is called for a missing app
    client = JujuClient(controller=mock_controller)
    result = await client.get_app_config("dev", "missing")
    # THEN an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_app_config_raises_juju_error_when_model_gone(mock_controller):
    # GIVEN the controller raises InvalidStatusCode (model was removed)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_app_config is called for the removed model
    # THEN a JujuError is raised instead of crashing
    with pytest.raises(JujuError, match="no longer available"):
        await client.get_app_config("removed-model", "pg")


# ─────────────────────────────────────────────────────────────────────────────
# get_relation_data
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_relation_data_provider_side(mock_controller):
    # GIVEN a model where the provider unit has application-level relation data
    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    _make_relation_model(mock_controller, {"postgresql": [unit_mock], "wordpress": []})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        ep_data = MagicMock()
        ep_data.relation_id = 5
        ep_data.endpoint = "db"
        ep_data.applicationdata = {"host": "10.0.0.1", "port": "5432"}
        ep_data.unit_relation_data = {}
        unit_result = MagicMock()
        unit_result.error = None
        unit_result.result = MagicMock()
        unit_result.result.relation_data = [ep_data]
        units_info_result = MagicMock()
        units_info_result.results = [unit_result]
        facade_inst.UnitsInfo = AsyncMock(return_value=units_info_result)
        # WHEN get_relation_data is called
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN RelationDataEntry objects are returned
    assert len(result) > 0
    assert all(isinstance(e, RelationDataEntry) for e in result)


@pytest.mark.asyncio
async def test_get_relation_data_no_units(mock_controller):
    # GIVEN apps with no units
    _make_relation_model(mock_controller, {"postgresql": [], "wordpress": []})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        MockFacade.from_connection = MagicMock(return_value=AsyncMock())
        # WHEN get_relation_data is called
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_relation_data_skips_wrong_relation_id(mock_controller):
    # GIVEN ep_data has a different relation_id than requested
    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    _make_relation_model(mock_controller, {"postgresql": [unit_mock]})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        ep_data = MagicMock()
        ep_data.relation_id = 99  # wrong — should be skipped
        ep_data.applicationdata = {"key": "val"}
        ep_data.unit_relation_data = {}
        unit_result = MagicMock()
        unit_result.error = None
        unit_result.result = MagicMock()
        unit_result.result.relation_data = [ep_data]
        units_info_result = MagicMock()
        units_info_result.results = [unit_result]
        facade_inst.UnitsInfo = AsyncMock(return_value=units_info_result)
        # WHEN get_relation_data is called for relation_id=5
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN the mismatched entry is skipped
    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# get_status_details — SAAS branches (lines 303-306, 316-318)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_details_saas_from_unknown_fields(mock_controller):
    # GIVEN a Juju 3.6+ model with SAAS in unknown_fields['application-endpoints']
    status = _make_status_mock(
        unknown_fields={
            "application-endpoints": {
                "remote-pg": {
                    "url": "mystore:admin/pg",
                    "application-status": {"current": "active"},
                },
                "remote-mysql": {
                    "url": "otherstore:admin/mysql",
                    "application-status": {"current": "blocked"},
                },
            }
        }
    )
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    model.applications = {}
    mock_controller.get_model.return_value = model
    # WHEN get_status_details is called
    client = JujuClient(controller=mock_controller)
    _, _, saas = await client.get_status_details("cos")
    # THEN both SAAS entries are parsed with store and status
    assert len(saas) == 2
    urls = {s.url for s in saas}
    assert "mystore:admin/pg" in urls
    assert "otherstore:admin/mysql" in urls
    stores = {s.store for s in saas}
    assert "mystore" in stores
    statuses = {s.status for s in saas}
    assert "active" in statuses
    assert "blocked" in statuses


@pytest.mark.asyncio
async def test_get_status_details_saas_from_remote_applications(mock_controller):
    # GIVEN a model with SAAS in status.remote_applications (pre-3.6 Juju)
    remote_st = MagicMock()
    remote_st.offer_url = "mystore:admin/mysql"
    remote_st.status.status = "waiting"
    status = _make_status_mock(remote_applications={"remote-mysql": remote_st})
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    model.applications = {}
    mock_controller.get_model.return_value = model
    # WHEN get_status_details is called
    client = JujuClient(controller=mock_controller)
    _, _, saas = await client.get_status_details("dev")
    # THEN the SAAS entry is parsed from remote_applications
    assert len(saas) == 1
    assert saas[0].url == "mystore:admin/mysql"
    assert saas[0].store == "mystore"
    assert saas[0].status == "waiting"
    assert saas[0].name == "remote-mysql"


# ─────────────────────────────────────────────────────────────────────────────
# get_status_details — model no longer available (InvalidStatusCode)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_details_raises_juju_error_when_model_gone(mock_controller):
    # GIVEN the controller raises InvalidStatusCode (model was removed)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_status_details is called for the removed model
    # THEN a JujuError is raised instead of crashing the app
    with pytest.raises(JujuError, match="no longer available"):
        await client.get_status_details("removed-model")


# ─────────────────────────────────────────────────────────────────────────────
# get_relation_data — peer, empty results, error result, unit-level data
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_relation_data_peer_relation(mock_controller):
    # GIVEN a peer relation (provider_app == requirer_app)
    unit_mock = MagicMock()
    unit_mock.name = "etcd/0"
    _make_relation_model(mock_controller, {"etcd": [unit_mock]})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        ep_data = MagicMock()
        ep_data.relation_id = 3
        ep_data.applicationdata = {"cluster-key": "value"}
        ep_data.unit_relation_data = {}
        unit_result = MagicMock()
        unit_result.error = None
        unit_result.result = MagicMock()
        unit_result.result.relation_data = [ep_data]
        units_info_result = MagicMock()
        units_info_result.results = [unit_result]
        facade_inst.UnitsInfo = AsyncMock(return_value=units_info_result)
        # WHEN get_relation_data is called with same app on both sides
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 3, "etcd", "etcd")
    # THEN all entries have side="peer"
    assert len(result) > 0
    assert all(e.side == "peer" for e in result)


@pytest.mark.asyncio
async def test_get_relation_data_empty_units_info_results(mock_controller):
    # GIVEN UnitsInfo returns a result with an empty results list
    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    _make_relation_model(mock_controller, {"postgresql": [unit_mock], "wordpress": []})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        empty_result = MagicMock()
        empty_result.results = []
        facade_inst.UnitsInfo = AsyncMock(return_value=empty_result)
        # WHEN get_relation_data is called
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN the empty result is skipped and an empty list is returned
    assert result == []


@pytest.mark.asyncio
async def test_get_relation_data_unit_result_has_error(mock_controller):
    # GIVEN a unit_result with a truthy error field
    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    _make_relation_model(mock_controller, {"postgresql": [unit_mock], "wordpress": []})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        unit_result = MagicMock()
        unit_result.error = MagicMock()  # truthy error → skip
        unit_result.result = MagicMock()
        units_info_result = MagicMock()
        units_info_result.results = [unit_result]
        facade_inst.UnitsInfo = AsyncMock(return_value=units_info_result)
        # WHEN get_relation_data is called
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN the errored result is skipped
    assert result == []


@pytest.mark.asyncio
async def test_get_relation_data_includes_unit_level_data(mock_controller):
    # GIVEN ep_data has unit_relation_data with unitdata entries
    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    _make_relation_model(mock_controller, {"postgresql": [unit_mock], "wordpress": []})
    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        unit_rel_data = MagicMock()
        unit_rel_data.unitdata = {"ingress-address": "10.1.2.3", "private-address": "10.0.0.1"}
        ep_data = MagicMock()
        ep_data.relation_id = 5
        ep_data.applicationdata = {}
        ep_data.unit_relation_data = {"wordpress/0": unit_rel_data}
        unit_result = MagicMock()
        unit_result.error = None
        unit_result.result = MagicMock()
        unit_result.result.relation_data = [ep_data]
        units_info_result = MagicMock()
        units_info_result.results = [unit_result]
        facade_inst.UnitsInfo = AsyncMock(return_value=units_info_result)
        # WHEN get_relation_data is called
        client = JujuClient(controller=mock_controller)
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")
    # THEN unit-level entries are included with correct keys and unit name
    unit_entries = [e for e in result if e.scope == "unit"]
    assert len(unit_entries) == 2
    keys = {e.key for e in unit_entries}
    assert keys == {"ingress-address", "private-address"}
    assert all(e.unit == "wordpress/0" for e in unit_entries)


@pytest.mark.asyncio
async def test_get_controller_offers_uses_status_counts(mock_controller):
    # GIVEN an offer with no connections in list_offers (non-admin) but counts in model status
    ep = MagicMock()
    ep.name = "metrics-endpoint"
    ep.interface = "prometheus_scrape"
    ep.role = "provider"
    offer = MagicMock()
    offer.offer_name = "prometheus-scrape"
    offer.offer_url = "admin/cos.prometheus-scrape"
    offer.application_name = "prometheus"
    offer.charm_url = "ch:prometheus-k8s-1"
    offer.application_description = "Scrape endpoint"
    offer.endpoints = [ep]
    offer.connections = []
    offer.users = []
    list_offers_result = MagicMock()
    list_offers_result.results = [offer]
    mock_controller.list_models = AsyncMock(return_value=["cos"])
    mock_controller.list_offers = AsyncMock(return_value=list_offers_result)
    offer_st = MagicMock()
    offer_st.active_connected_count = 1
    offer_st.total_connected_count = 1
    status = MagicMock()
    status.offers = {"prometheus-scrape": offer_st}
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    model.disconnect = AsyncMock()
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_controller_offers is called
    client = JujuClient(controller=mock_controller)
    results = await client.get_controller_offers()
    # THEN connection counts come from model status, not the offer object
    assert len(results) == 1
    info: ControllerOfferInfo = results[0]
    assert info.active_connections == 1
    assert info.total_connections == 1


@pytest.mark.asyncio
async def test_get_relation_data_raises_juju_error_when_model_gone(mock_controller):
    # GIVEN the controller raises InvalidStatusCode (model was removed)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_relation_data is called for the removed model
    # THEN a JujuError is raised instead of crashing
    with pytest.raises(JujuError, match="no longer available"):
        await client.get_relation_data("removed-model", 1, "pg", "wp")


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper functions
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ts_raw, expected_len",
    [
        pytest.param("2024-03-07T15:30:45.123456789Z", 8, id="nanosecond-ts"),
        pytest.param("2024-03-07T15:30:45Z", 8, id="no-fractional"),
    ],
)
def test_utc_ts_to_local_hms_valid(ts_raw: str, expected_len: int) -> None:
    # GIVEN a valid Juju RFC3339 timestamp with or without nanoseconds
    # WHEN _utc_ts_to_local_hms is called
    result = _utc_ts_to_local_hms(ts_raw)
    # THEN the result is an HH:MM:SS string
    assert len(result) == expected_len
    assert result.count(":") == 2


@pytest.mark.parametrize(
    "ts_raw, expected",
    [
        pytest.param("not-a-valid-timestamp", "not-a-va", id="no-T-fallback"),
        pytest.param("garbage-T99:99:99", "99:99:99", id="with-T-fallback"),
    ],
)
def test_utc_ts_to_local_hms_invalid(ts_raw: str, expected: str) -> None:
    # GIVEN a timestamp that cannot be parsed by fromisoformat
    # WHEN _utc_ts_to_local_hms is called
    result = _utc_ts_to_local_hms(ts_raw)
    # THEN the fallback value is returned
    assert result == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(None, "", id="none"),
        pytest.param(b"hello", "hello", id="bytes"),
        pytest.param("world", "world", id="str"),
        pytest.param(42, "42", id="int"),
    ],
)
def test_s_coercion(value: object, expected: str) -> None:
    # GIVEN a value of various types
    # WHEN _s is called
    result = _s(value)
    # THEN it is coerced to str correctly
    assert result == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        pytest.param("aGVsbG8=", "hello", id="valid-base64"),
        pytest.param("not-base64!", "not-base64!", id="invalid-base64-returns-raw"),
    ],
)
def test_decode_secret_value(raw: str, expected: str) -> None:
    # GIVEN a raw string that may or may not be valid base64
    # WHEN _decode_secret_value is called
    result = _decode_secret_value(raw)
    # THEN valid base64 is decoded, invalid is returned as-is
    assert result == expected


def test_parse_relation_returns_none_when_no_valid_endpoints() -> None:
    # GIVEN a relation with only one "provider" endpoint and no requirer or peer
    rel = MagicMock()
    rel.interface = "pgsql"
    rel.id_ = 1
    ep = MagicMock()
    ep.role = "provider"
    ep.application = "pg"
    ep.name = "db"
    rel.endpoints = [ep]
    # WHEN _parse_relation is called
    result = _parse_relation(rel, "dev", "prod")
    # THEN None is returned
    assert result is None


def test_parse_app_relation_data_empty_applicationdata() -> None:
    # GIVEN ep_data with no applicationdata
    ep_data = MagicMock()
    ep_data.applicationdata = {}
    # WHEN _parse_app_relation_data is called
    result = _parse_app_relation_data(ep_data, "requirer", "wordpress")
    # THEN an empty list is returned
    assert result == []


def test_parse_unit_relation_data_skips_falsy_rel_data() -> None:
    # GIVEN ep_data where one unit has a falsy rel_data entry
    ep_data = MagicMock()
    ep_data.unit_relation_data = {"wp/0": None}
    # WHEN _parse_unit_relation_data is called
    result = _parse_unit_relation_data(ep_data, "requirer")
    # THEN the None entry is skipped
    assert result == []


def test_parse_unit_relation_data_skips_empty_unitdata() -> None:
    # GIVEN ep_data where rel_data exists but unitdata is empty
    rel_data = MagicMock()
    rel_data.unitdata = {}
    ep_data = MagicMock()
    ep_data.unit_relation_data = {"wp/0": rel_data}
    # WHEN _parse_unit_relation_data is called
    result = _parse_unit_relation_data(ep_data, "requirer")
    # THEN the empty unitdata entry is skipped
    assert result == []


def test_offer_status_counts_skips_none_offer() -> None:
    # GIVEN a status.offers dict with a None value
    status = MagicMock()
    status.offers = {
        "valid-offer": MagicMock(active_connected_count=1, total_connected_count=2),
        "null-offer": None,
    }
    # WHEN _offer_status_counts is called
    counts = _offer_status_counts(status)
    # THEN the None offer is skipped and the valid one is returned
    assert "null-offer" not in counts
    assert counts["valid-offer"] == (1, 2)


@pytest.mark.asyncio
async def test_resolve_model_uuid_not_found() -> None:
    # GIVEN a controller with no matching model UUID
    controller = AsyncMock()
    controller.model_uuids = AsyncMock(return_value={"other-model": "uuid-999"})
    # WHEN _resolve_model_uuid is called for a missing model
    # THEN JujuClientError is raised
    with pytest.raises(JujuClientError, match="not found"):
        await _resolve_model_uuid(controller, "missing")


def test_log_stream_connection_params_with_list_endpoint() -> None:
    # GIVEN a controller where endpoint is a list
    conn = MagicMock()
    conn.connect_params.return_value = {
        "endpoint": ["10.0.0.1:17070", "10.0.0.2:17070"],
        "password": "secret",
        "cacert": None,
    }
    conn.username = "admin"
    controller = MagicMock()
    controller.connection.return_value = conn
    # WHEN _log_stream_connection_params is called
    endpoint, username, password, cacert = _log_stream_connection_params(controller)
    # THEN the first endpoint is selected
    assert endpoint == "10.0.0.1:17070"
    assert username == "admin"
    assert password == "secret"
    assert cacert is None


def test_log_stream_connection_params_raises_without_password() -> None:
    # GIVEN a controller with no password (token-based auth)
    conn = MagicMock()
    conn.connect_params.return_value = {
        "endpoint": "10.0.0.1:17070",
        "password": "",
        "cacert": None,
    }
    conn.username = "admin"
    controller = MagicMock()
    controller.connection.return_value = conn
    # WHEN _log_stream_connection_params is called
    # THEN JujuClientError is raised
    with pytest.raises(JujuClientError, match="username/password"):
        _log_stream_connection_params(controller)


def test_build_log_stream_url() -> None:
    # GIVEN connection parameters
    # WHEN _build_log_stream_url is called
    url = _build_log_stream_url("10.0.0.1:17070", "admin", "secret", "uuid-123", "DEBUG")
    # THEN the URL has the correct wss:// format with all parameters
    assert url.startswith("wss://")
    assert "uuid-123" in url
    assert "level=DEBUG" in url


@pytest.mark.parametrize(
    "cacert, expect_ctx",
    [
        pytest.param(None, False, id="no-cacert-returns-True"),
        pytest.param(
            "-----BEGIN CERTIFICATE-----\nMIIBIjANBgkqhkiG9w0B",
            True,
            id="cacert-returns-SSLContext",
        ),
    ],
)
def test_build_ssl_context(cacert: str | None, expect_ctx: bool) -> None:
    # GIVEN a cacert value (or None)
    # WHEN _build_ssl_context is called
    with patch("ssl.create_default_context") as mock_ssl:
        ctx_mock = MagicMock(spec=ssl.SSLContext)
        mock_ssl.return_value = ctx_mock
        result = _build_ssl_context(cacert)
    # THEN an SSLContext is returned when cacert is present, True otherwise
    if expect_ctx:
        assert result is ctx_mock
    else:
        assert result is True


def test_parse_log_entry() -> None:
    # GIVEN a valid JSON WebSocket message from the Juju log endpoint
    message = json.dumps(
        {
            "ts": "2024-01-01T12:00:00.000000Z",
            "sev": "INFO",
            "tag": "unit:pg/0",
            "mod": "juju.worker",
            "msg": "started",
        }
    )
    # WHEN _parse_log_entry is called
    entry = _parse_log_entry(message)
    # THEN all fields are populated correctly
    assert entry.level == "INFO"
    assert entry.entity == "unit:pg/0"
    assert entry.module == "juju.worker"
    assert entry.message == "started"


# ─────────────────────────────────────────────────────────────────────────────
# get_model_snapshot — None guards
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_model_snapshot_skips_none_app_st(mock_controller):
    # GIVEN full_status.applications contains a None value
    model, _, _ = _make_model_mock()
    full_status = MagicMock()
    full_status.applications = {"postgresql": None}  # None app_st should be skipped
    full_status.machines = {}
    full_status.relations = []
    model.get_status = AsyncMock(return_value=full_status)
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, apps, units, _ = await client.get_model_snapshot("dev")
    # THEN the None app_st is skipped
    assert apps == []
    assert units == []


@pytest.mark.asyncio
async def test_get_model_snapshot_skips_none_unit_st(mock_controller):
    # GIVEN an app_st.units dict with a None unit value
    model, app_st, _ = _make_model_mock()
    app_st.units = {"postgresql/0": None}  # None unit_st should be skipped
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, _, units, _ = await client.get_model_snapshot("dev")
    # THEN the None unit_st is skipped
    assert units == []


@pytest.mark.asyncio
async def test_get_model_snapshot_skips_none_subordinate(mock_controller):
    # GIVEN a unit with a subordinates dict containing a None value
    model, app_st, unit_st = _make_model_mock()
    unit_st.subordinates = {"nrpe/0": None}  # None subordinate should be skipped
    mock_controller.get_model.return_value = model
    # WHEN get_model_snapshot is called
    client = JujuClient(controller=mock_controller)
    _, _, units, _ = await client.get_model_snapshot("dev")
    # THEN the None subordinate is skipped; only the principal unit is returned
    assert len(units) == 1
    assert units[0].name == "postgresql/0"


# ─────────────────────────────────────────────────────────────────────────────
# get_secret_content
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_secret_content_returns_decoded_data(mock_controller):
    # GIVEN a model with a secret whose value has base64-encoded data
    encoded = base64.b64encode(b"supersecret").decode()
    model = AsyncMock()
    secret = MagicMock()
    secret.uri = "secret:abc123"
    secret.value = MagicMock()
    secret.value.data = {"password": encoded}
    model.list_secrets = AsyncMock(return_value=[secret])
    model.disconnect = AsyncMock()
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_secret_content is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_secret_content("dev", "secret:abc123")
    # THEN the decoded value is returned
    assert result == {"password": "supersecret"}


@pytest.mark.asyncio
async def test_get_secret_content_returns_empty_when_not_found(mock_controller):
    # GIVEN a model with a secret that doesn't match the URI
    model = AsyncMock()
    secret = MagicMock()
    secret.uri = "secret:other"
    model.list_secrets = AsyncMock(return_value=[secret])
    model.disconnect = AsyncMock()
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_secret_content is called for a different URI
    client = JujuClient(controller=mock_controller)
    result = await client.get_secret_content("dev", "secret:nothere")
    # THEN an empty dict is returned
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "secret_value",
    [
        pytest.param(None, id="value-is-none"),
        pytest.param(MagicMock(data=None), id="data-is-none"),
    ],
)
async def test_get_secret_content_skips_missing_data(mock_controller, secret_value) -> None:
    # GIVEN a secret that matches the URI but has no usable content
    model = AsyncMock()
    secret = MagicMock()
    secret.uri = "secret:abc123"
    secret.value = secret_value
    model.list_secrets = AsyncMock(return_value=[secret])
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_secret_content is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_secret_content("dev", "secret:abc123")
    # THEN an empty dict is returned
    assert result == {}


@pytest.mark.asyncio
async def test_get_secret_content_raises_juju_error_when_model_gone(mock_controller):
    # GIVEN the controller raises InvalidStatusCode (model was removed)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_secret_content is called for the removed model
    # THEN a JujuError is raised instead of crashing
    with pytest.raises(JujuError, match="no longer available"):
        await client.get_secret_content("removed-model", "secret:abc123")


# ─────────────────────────────────────────────────────────────────────────────
# get_saas
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_saas_delegates_to_get_status_details(mock_controller):
    # GIVEN get_status_details is mocked to return a known SAAS list
    client = JujuClient(controller=mock_controller)
    expected = [MagicMock()]
    with patch.object(client, "get_status_details", new=AsyncMock(return_value=([], [], expected))):
        # WHEN get_saas is called
        result = await client.get_saas("dev")
    # THEN the SAAS list from get_status_details is returned unchanged
    assert result is expected


# ─────────────────────────────────────────────────────────────────────────────
# get_offer_detail
# ─────────────────────────────────────────────────────────────────────────────


def _make_offer_model(mock_controller: MagicMock) -> None:
    """Configure mock_controller with a minimal model for get_offer_detail tests."""
    status = MagicMock()
    status.offers = {}
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    mock_controller.get_model = AsyncMock(return_value=model)


@pytest.mark.asyncio
async def test_get_offer_detail_found(mock_controller):
    # GIVEN a model with a named offer
    ep = MagicMock()
    ep.name = "db"
    ep.interface = "pgsql"
    ep.role = "provider"
    offer = MagicMock()
    offer.offer_name = "pg-offer"
    offer.offer_url = "admin/dev.pg-offer"
    offer.application_name = "postgresql"
    offer.charm_url = "ch:postgresql"
    offer.application_description = "PG offer"
    offer.endpoints = [ep]
    offer.users = []
    raw = MagicMock()
    raw.results = [offer]
    mock_controller.list_offers = AsyncMock(return_value=raw)
    _make_offer_model(mock_controller)
    # WHEN get_offer_detail is called with the correct offer name
    client = JujuClient(controller=mock_controller)
    result = await client.get_offer_detail("dev", "pg-offer")
    # THEN the ControllerOfferInfo is returned
    assert result is not None
    assert result.name == "pg-offer"
    assert result.application == "postgresql"


@pytest.mark.asyncio
async def test_get_offer_detail_not_found_returns_none(mock_controller):
    # GIVEN a model where list_offers returns a different offer name
    offer = MagicMock()
    offer.offer_name = "other-offer"
    raw = MagicMock()
    raw.results = [offer]
    mock_controller.list_offers = AsyncMock(return_value=raw)
    _make_offer_model(mock_controller)
    # WHEN get_offer_detail is called for a non-existent offer
    client = JujuClient(controller=mock_controller)
    result = await client.get_offer_detail("dev", "pg-offer")
    # THEN None is returned
    assert result is None


@pytest.mark.asyncio
async def test_get_offer_detail_returns_none_on_juju_error(mock_controller):
    # GIVEN list_offers raises JujuError
    mock_controller.list_offers = AsyncMock(side_effect=JujuError("boom"))
    # WHEN get_offer_detail is called
    client = JujuClient(controller=mock_controller)
    result = await client.get_offer_detail("dev", "pg-offer")
    # THEN None is returned (error is swallowed)
    assert result is None


@pytest.mark.asyncio
async def test_get_offer_detail_returns_none_when_model_gone(mock_controller):
    # GIVEN list_offers succeeds but get_model raises InvalidStatusCode
    raw = MagicMock()
    raw.results = []
    mock_controller.list_offers = AsyncMock(return_value=raw)
    mock_controller.get_model = AsyncMock(
        side_effect=websockets.exceptions.InvalidStatusCode(400, None)
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_offer_detail is called for the removed model
    # THEN None is returned instead of crashing
    result = await client.get_offer_detail("removed-model", "pg-offer")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# get_controller_offers — JujuError per-model fallback
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_controller_offers_skips_model_on_juju_error(mock_controller):
    # GIVEN two models where the first raises JujuError on list_offers
    mock_controller.list_models = AsyncMock(return_value=["broken", "ok"])
    ep = MagicMock()
    ep.name = "db"
    ep.interface = "pgsql"
    ep.role = "provider"
    offer = MagicMock()
    offer.offer_name = "pg-offer"
    offer.offer_url = "admin/ok.pg-offer"
    offer.application_name = "postgresql"
    offer.charm_url = "ch:postgresql"
    offer.application_description = ""
    offer.endpoints = [ep]
    offer.users = []
    raw = MagicMock()
    raw.results = [offer]
    mock_controller.list_offers = AsyncMock(side_effect=[JujuError("boom"), raw])
    status = MagicMock()
    status.offers = {}
    model = AsyncMock()
    model.get_status = AsyncMock(return_value=status)
    model.disconnect = AsyncMock()
    mock_controller.get_model = AsyncMock(return_value=model)
    # WHEN get_controller_offers is called
    client = JujuClient(controller=mock_controller)
    results = await client.get_controller_offers()
    # THEN the broken model is skipped and the ok model's offer is returned
    assert len(results) == 1
    assert results[0].name == "pg-offer"


@pytest.mark.asyncio
async def test_get_controller_offers_skips_model_when_model_gone(mock_controller):
    # GIVEN two models where the first raises InvalidStatusCode on get_model
    mock_controller.list_models = AsyncMock(return_value=["gone", "ok"])
    ep = MagicMock()
    ep.name = "db"
    ep.interface = "pgsql"
    ep.role = "provider"
    offer = MagicMock()
    offer.offer_name = "pg-offer"
    offer.offer_url = "admin/ok.pg-offer"
    offer.application_name = "postgresql"
    offer.charm_url = "ch:postgresql"
    offer.application_description = ""
    offer.endpoints = [ep]
    offer.users = []
    raw = MagicMock()
    raw.results = [offer]
    mock_controller.list_offers = AsyncMock(return_value=raw)
    status = MagicMock()
    status.offers = {}
    ok_model = AsyncMock()
    ok_model.get_status = AsyncMock(return_value=status)
    ok_model.disconnect = AsyncMock()
    mock_controller.get_model = AsyncMock(
        side_effect=[websockets.exceptions.InvalidStatusCode(400, None), ok_model]
    )
    client = JujuClient(controller=mock_controller)

    # WHEN get_controller_offers is called
    # THEN the gone model is skipped and the ok model's offer is returned
    results = await client.get_controller_offers()
    assert len(results) == 1
    assert results[0].name == "pg-offer"


# ─────────────────────────────────────────────────────────────────────────────
# stream_logs
# ─────────────────────────────────────────────────────────────────────────────


def _make_ws_cm(messages: list[str]) -> AsyncMock:
    """Build a websocket context manager that yields messages then raises CancelledError."""

    async def fake_ws_iter():
        for msg in messages:
            yield msg
        raise asyncio.CancelledError

    ws_mock = MagicMock()
    ws_mock.__aiter__ = lambda self: fake_ws_iter()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=ws_mock)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_stream_logs_yields_entries(mock_controller):
    # GIVEN a model UUID and websocket that yields one message then raises CancelledError
    _make_stream_logs_controller(mock_controller)
    msg = json.dumps(
        {
            "ts": "2024-01-01T12:00:00.000000Z",
            "sev": "INFO",
            "tag": "unit:pg/0",
            "mod": "juju.worker",
            "msg": "started",
        }
    )
    cm = _make_ws_cm([msg])
    # WHEN stream_logs is iterated
    with patch("websockets.connect", return_value=cm):
        client = JujuClient(controller=mock_controller)
        entries = []
        try:
            async for entry in client.stream_logs("dev"):
                entries.append(entry)
        except asyncio.CancelledError:
            pass
    # THEN the parsed log entry is yielded
    assert len(entries) == 1
    assert entries[0].level == "INFO"
    assert entries[0].entity == "unit:pg/0"


@pytest.mark.asyncio
async def test_stream_logs_exits_on_generic_exception(mock_controller):
    # GIVEN a websocket connection that raises a generic Exception
    _make_stream_logs_controller(mock_controller)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("unexpected"))
    cm.__aexit__ = AsyncMock(return_value=False)

    # WHEN stream_logs is iterated
    with patch("websockets.connect", return_value=cm):
        client = JujuClient(controller=mock_controller)
        entries = []
        async for entry in client.stream_logs("dev"):
            entries.append(entry)  # pragma: no cover

    # THEN the generator exits cleanly with no entries
    assert entries == []


@pytest.mark.asyncio
async def test_stream_logs_reconnects_on_connection_closed(mock_controller):
    # GIVEN first connection raises ConnectionClosed, second raises generic Exception to exit
    _make_stream_logs_controller(mock_controller)

    call_count = 0

    async def fake_aenter(self):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise websockets.ConnectionClosed(None, None)
        raise RuntimeError("exit")

    cm = MagicMock()
    cm.__aenter__ = fake_aenter
    cm.__aexit__ = AsyncMock(return_value=False)

    # WHEN stream_logs is iterated (with mocked sleep to avoid real delay)
    with (
        patch("websockets.connect", return_value=cm),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        client = JujuClient(controller=mock_controller)
        entries = []
        async for entry in client.stream_logs("dev"):
            entries.append(entry)  # pragma: no cover

    # THEN it attempted to reconnect (call_count == 2)
    assert call_count == 2
    assert entries == []


@pytest.mark.asyncio
async def test_stream_logs_skips_invalid_json_message(mock_controller):
    # GIVEN a websocket that yields an invalid JSON message then raises CancelledError
    _make_stream_logs_controller(mock_controller)
    cm = _make_ws_cm(["not valid json {"])
    # WHEN stream_logs is iterated
    with patch("websockets.connect", return_value=cm):
        client = JujuClient(controller=mock_controller)
        entries = []
        try:
            async for entry in client.stream_logs("dev"):
                entries.append(entry)
        except asyncio.CancelledError:
            pass
    # THEN the invalid message is skipped and no entries are yielded
    assert entries == []


# ─────────────────────────────────────────────────────────────────────────────
# _parse_machine_info — extended fields
# ─────────────────────────────────────────────────────────────────────────────


def _make_machine_mock(
    hardware="arch=amd64 cores=4 mem=16384M root-disk=51200M virt-type=kvm "
    "availability-zone=us-east-1a",
    agent_since=None,
    instance_status="running",
    instance_since=None,
    network_interfaces=None,
):
    m = MagicMock()
    m.agent_status.status = "started"
    m.agent_status.since = agent_since
    m.dns_name = "10.0.0.1"
    m.instance_id = "i-abc123"
    m.base.name = "ubuntu"
    m.base.channel = "22.04"
    m.hardware = hardware
    m.instance_status.status = instance_status
    m.instance_status.info = "ready"
    m.instance_status.since = instance_since
    m.network_interfaces = network_interfaces
    return m


def test_parse_machine_info_parses_hardware_fields():
    # GIVEN a machine mock with a full hardware string
    m_st = _make_machine_mock()

    # WHEN _parse_machine_info is called
    result = _parse_machine_info("0", m_st, "dev", "ctrl")

    # THEN all hardware fields are correctly parsed
    assert result.hardware_arch == "amd64"
    assert result.hardware_cores == 4
    assert result.hardware_mem_mib == 16384
    assert result.hardware_disk_mib == 51200
    assert result.hardware_virt_type == "kvm"
    assert result.az == "us-east-1a"


def test_parse_machine_info_parses_network_interfaces():
    # GIVEN a machine mock with one interface that has both IPv4 and IPv6 addresses
    # ip_addresses in python-libjuju is Sequence[str] — plain strings, not objects
    iface = MagicMock()
    iface.ip_addresses = ["10.0.0.1", "fe80::1"]
    iface.mac_address = "52:54:00:aa:bb:cc"
    iface.space = "alpha"
    m_st = _make_machine_mock(network_interfaces={"eth0": iface})

    # WHEN _parse_machine_info is called
    result = _parse_machine_info("0", m_st, "dev", "ctrl")

    # THEN all IP addresses are captured for the interface
    assert len(result.network_interfaces) == 1
    nic = result.network_interfaces[0]
    assert nic.name == "eth0"
    assert nic.ips == ["10.0.0.1", "fe80::1"]
    assert nic.mac == "52:54:00:aa:bb:cc"
    assert nic.space == "alpha"


def test_parse_machine_info_no_network_interfaces_returns_empty_list():
    # GIVEN a machine mock with no network interfaces
    m_st = _make_machine_mock(network_interfaces=None)

    # WHEN _parse_machine_info is called
    result = _parse_machine_info("0", m_st, "dev", "ctrl")

    # THEN network_interfaces is an empty list
    assert result.network_interfaces == []


# ─────────────────────────────────────────────────────────────────────────────
# _parse_hw
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "hw_string, expected",
    [
        pytest.param(
            "arch=amd64 cores=4 mem=16384M root-disk=51200M virt-type=kvm "
            "availability-zone=us-east-1a",
            {
                "arch": "amd64",
                "cores": 4,
                "mem": 16384,
                "root-disk": 51200,
                "virt-type": "kvm",
                "availability-zone": "us-east-1a",
            },
            id="all-known-fields",
        ),
        pytest.param(
            "arch=amd64 cores=notanumber mem=badM root-disk=alsoM virt-type=kvm",
            {"arch": "amd64", "virt-type": "kvm"},
            id="invalid-numeric-ignored",
        ),
        pytest.param("", {}, id="empty-string"),
        pytest.param("arch=amd64 future-field=value", {"arch": "amd64"}, id="unknown-keys-ignored"),
    ],
)
def test_parse_hw(hw_string: str, expected: dict) -> None:
    # GIVEN a hardware string
    # WHEN _parse_hw is called
    result = _parse_hw(hw_string)

    # THEN the result matches the expected dict
    assert result == expected


# ─────────────────────────────────────────────────────────────────────────────
# _since_to_iso
# ─────────────────────────────────────────────────────────────────────────────


def test_since_to_iso_returns_empty_for_none():
    # GIVEN a None value
    # WHEN _since_to_iso is called
    result = _since_to_iso(None)
    # THEN an empty string is returned
    assert result == ""


def test_since_to_iso_calls_isoformat_on_datetime():
    # GIVEN a datetime object
    from datetime import datetime, timezone

    dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    # WHEN _since_to_iso is called
    result = _since_to_iso(dt)

    # THEN the ISO string from isoformat() is returned
    assert result == dt.isoformat()


def test_since_to_iso_falls_back_to_str_when_no_isoformat():
    # GIVEN a value with no isoformat() method (plain string)
    # WHEN _since_to_iso is called
    result = _since_to_iso("2024-01-15T10:30:00")

    # THEN the string representation is returned as fallback
    assert result == "2024-01-15T10:30:00"
