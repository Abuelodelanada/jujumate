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
    info = MagicMock()
    info.cloud_tag = "cloud-aws"
    info.cloud_region = "us-east-1"
    info.status.current = "available"
    info.machines = []
    info.applications = {"postgresql": MagicMock()}
    mock_controller.get_model_info.return_value = info

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
async def test_get_models_skips_failed_model(mock_controller):
    mock_controller.list_models.return_value = ["broken", "ok"]
    ok_info = MagicMock()
    ok_info.cloud_tag = "cloud-aws"
    ok_info.cloud_region = "us-east-1"
    ok_info.status.current = "available"
    ok_info.machines = []
    ok_info.applications = {}
    mock_controller.get_model_info.side_effect = [Exception("boom"), ok_info]

    client = JujuClient()
    result = await client.get_models()

    assert len(result) == 1
    assert result[0].name == "ok"


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
