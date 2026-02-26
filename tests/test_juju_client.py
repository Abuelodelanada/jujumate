from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jujumate.client.juju_client import JujuClient, JujuClientError


@pytest.fixture
def mock_controller():
    with patch("jujumate.client.juju_client.Controller") as MockController:
        ctrl = AsyncMock()
        ctrl.controller_name = "test-controller"
        MockController.return_value = ctrl
        yield ctrl


@pytest.mark.asyncio
async def test_connect_current(mock_controller):
    client = JujuClient()
    await client.connect()
    mock_controller.connect_current.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_named_controller(mock_controller):
    client = JujuClient(controller_name="prod")
    await client.connect()
    mock_controller.connect.assert_awaited_once_with("prod")


@pytest.mark.asyncio
async def test_connect_raises_on_failure(mock_controller):
    mock_controller.connect_current.side_effect = Exception("connection refused")
    client = JujuClient()
    with pytest.raises(JujuClientError, match="Failed to connect"):
        await client.connect()


@pytest.mark.asyncio
async def test_context_manager_connects_and_disconnects(mock_controller):
    async with JujuClient():
        mock_controller.connect_current.assert_awaited_once()
    mock_controller.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_clouds(mock_controller):
    region = MagicMock()
    region.name = "us-east-1"
    cloud = MagicMock()
    cloud.type_ = "ec2"
    cloud.regions = [region]
    mock_controller.clouds.return_value = MagicMock(clouds={"cloud-aws": cloud})

    client = JujuClient()
    result = await client.get_clouds()

    assert len(result) == 1
    assert result[0].name == "aws"
    assert result[0].type == "ec2"
    assert result[0].regions == ["us-east-1"]


@pytest.mark.asyncio
async def test_get_models(mock_controller):
    mock_controller.list_models.return_value = ["dev", "prod"]
    model = AsyncMock()
    info = MagicMock()
    info.cloud_tag = "cloud-aws"
    info.cloud_region = "us-east-1"
    info.status.status = "available"
    model.info = info
    model.machines = {}
    model.applications = {"postgresql": MagicMock()}
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_models()

    assert len(result) == 2
    assert result[0].name == "dev"
    assert result[0].cloud == "aws"
    assert result[0].app_count == 1


@pytest.mark.asyncio
async def test_get_applications(mock_controller):
    app = MagicMock()
    app.name = "postgresql"
    app.charm_name = "postgresql"
    app.data = {"charm-channel": "14/stable", "charm-rev": "363"}
    app.units = [MagicMock()]
    app.status = "active"
    app.status_message = ""
    model = AsyncMock()
    model.applications = {"postgresql": app}
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_applications("dev")

    assert len(result) == 1
    assert result[0].name == "postgresql"
    assert result[0].channel == "14/stable"
    assert result[0].revision == 363
    assert result[0].unit_count == 1


@pytest.mark.asyncio
async def test_get_units(mock_controller):
    unit = MagicMock()
    unit.name = "postgresql/0"
    unit.application = "postgresql"
    unit.machine_id = "0"
    unit.workload_status = "active"
    unit.agent_status = "idle"
    unit.public_address = "10.0.0.1"
    model = AsyncMock()
    model.units = {"postgresql/0": unit}
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_units("dev")

    assert len(result) == 1
    assert result[0].name == "postgresql/0"
    assert result[0].address == "10.0.0.1"


@pytest.mark.asyncio
async def test_get_models_falls_back_on_failed_model(mock_controller):
    mock_controller.list_models.return_value = ["broken", "ok"]
    ok_model = AsyncMock()
    ok_info = MagicMock()
    ok_info.cloud_tag = "cloud-aws"
    ok_info.cloud_region = "us-east-1"
    ok_info.status.status = "available"
    ok_model.info = ok_info
    ok_model.machines = {}
    ok_model.applications = {}
    mock_controller.get_model.side_effect = [Exception("boom"), ok_model]

    client = JujuClient()
    result = await client.get_models()

    # Both models are returned: one with full info, one minimal (fallback)
    assert len(result) == 2
    broken = next(m for m in result if m.name == "broken")
    assert broken.status == "unknown"
    assert broken.cloud == ""
    ok = next(m for m in result if m.name == "ok")
    assert ok.cloud == "aws"


@pytest.mark.asyncio
async def test_get_applications_returns_empty_on_failure(mock_controller):
    mock_controller.get_model.side_effect = Exception("boom")

    client = JujuClient()
    result = await client.get_applications("broken-model")

    assert result == []


@pytest.mark.asyncio
async def test_get_units_returns_empty_on_failure(mock_controller):
    mock_controller.get_model.side_effect = Exception("boom")

    client = JujuClient()
    result = await client.get_units("broken-model")

    assert result == []


@pytest.mark.asyncio
async def test_get_controllers(mock_controller):
    conn = MagicMock()
    conn.info = {"server-version": "3.4.0"}
    mock_controller.connection = MagicMock(return_value=conn)
    mock_controller.get_cloud = AsyncMock(return_value="aws")
    mock_controller.list_models = AsyncMock(return_value=["dev", "prod"])

    client = JujuClient()
    result = await client.get_controllers()

    assert len(result) == 1
    assert result[0].name == "test-controller"
    assert result[0].cloud == "aws"
    assert result[0].juju_version == "3.4.0"
    assert result[0].model_count == 2


@pytest.mark.asyncio
async def test_get_controllers_returns_empty_on_failure(mock_controller):
    mock_controller.get_cloud.side_effect = Exception("boom")

    client = JujuClient()
    result = await client.get_controllers()

    assert result == []


@pytest.mark.asyncio
async def test_get_relations(mock_controller):
    from jujumate.models.entities import RelationInfo

    model = AsyncMock()
    status = MagicMock()
    rel = MagicMock()
    rel.interface = "pgsql"
    rel.scope = "global"
    provider_ep = MagicMock()
    provider_ep.application = "postgresql"
    provider_ep.name = "db"
    provider_ep.role = "provider"
    requirer_ep = MagicMock()
    requirer_ep.application = "wordpress"
    requirer_ep.name = "db"
    requirer_ep.role = "requirer"
    rel.endpoints = [provider_ep, requirer_ep]
    status.relations = [rel]
    model.get_status = AsyncMock(return_value=status)
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_relations("dev")

    assert len(result) == 1
    assert result[0].provider == "postgresql:db"
    assert result[0].requirer == "wordpress:db"
    assert result[0].interface == "pgsql"
    assert result[0].type == "regular"
    assert result[0].model == "dev"


@pytest.mark.asyncio
async def test_get_relations_peer(mock_controller):
    model = AsyncMock()
    status = MagicMock()
    rel = MagicMock()
    rel.interface = "etcd"
    peer_ep = MagicMock()
    peer_ep.application = "etcd"
    peer_ep.name = "cluster"
    peer_ep.role = "peer"
    rel.endpoints = [peer_ep]
    status.relations = [rel]
    model.get_status = AsyncMock(return_value=status)
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_relations("dev")

    assert len(result) == 1
    assert result[0].provider == "etcd:cluster"
    assert result[0].requirer == "etcd:cluster"
    assert result[0].type == "peer"


@pytest.mark.asyncio
async def test_get_relations_returns_empty_on_failure(mock_controller):
    mock_controller.get_model.side_effect = Exception("boom")

    client = JujuClient()
    result = await client.get_relations("broken-model")

    assert result == []
