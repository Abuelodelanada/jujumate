from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jujumate.client.juju_client import JujuClient, JujuClientError


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
    model, _, _ = _make_model_mock()
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_models()

    assert len(result) == 2
    assert result[0].name == "dev"
    assert result[0].cloud == "aws"
    assert result[0].app_count == 1


@pytest.mark.asyncio
async def test_list_model_names(mock_controller):
    mock_controller.list_models.return_value = ["dev", "prod"]
    client = JujuClient()
    result = await client.list_model_names()
    assert result == ["dev", "prod"]


def _make_model_mock(app_name="postgresql", charm_name="postgresql", channel="14/stable",
                     revision=363, unit_name="postgresql/0", unit_address="10.0.0.1",
                     is_kubernetes=False):
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


@pytest.mark.asyncio
async def test_get_model_snapshot(mock_controller):
    model, app_st, unit_st = _make_model_mock()
    mock_controller.get_model.return_value = model

    client = JujuClient()
    model_info, apps, units, machines = await client.get_model_snapshot("dev")

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
    model, _, _ = _make_model_mock(is_kubernetes=True, unit_address="10.1.2.3")
    mock_controller.get_model.return_value = model

    client = JujuClient()
    model_info, apps, units, machines = await client.get_model_snapshot("cos")

    assert model_info.is_kubernetes is True
    assert model_info.machine_count == 0
    assert units[0].machine == ""
    assert units[0].address == "10.1.2.3"
    assert units[0].public_address == ""
    assert machines == []


@pytest.mark.asyncio
async def test_get_model_snapshot_fallback_on_failure(mock_controller):
    mock_controller.get_model.side_effect = Exception("timeout")
    client = JujuClient()
    model_info, apps, units, machines = await client.get_model_snapshot("broken")
    assert model_info.status == "unknown"
    assert apps == []
    assert units == []
    assert machines == []


@pytest.mark.asyncio
async def test_get_model_snapshot_includes_subordinate_units(mock_controller):
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

    client = JujuClient()
    _, _, units, _ = await client.get_model_snapshot("dev")

    assert len(units) == 2
    sub = next(u for u in units if u.name == "nrpe/0")
    assert sub.app == "nrpe"
    assert sub.subordinate_of == "postgresql/0"
    assert sub.machine == "0"
    assert sub.message == "Unit is ready"


@pytest.mark.asyncio
async def test_get_applications(mock_controller):
    model, _, _ = _make_model_mock()
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
    model, _, _ = _make_model_mock(unit_address="10.0.0.1")
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_units("dev")

    assert len(result) == 1
    assert result[0].name == "postgresql/0"
    assert result[0].public_address == "10.0.0.1"
    assert result[0].ports == "5432/tcp"
    assert result[0].message == "ready"


@pytest.mark.asyncio
async def test_get_models_falls_back_on_failed_model(mock_controller):
    mock_controller.list_models.return_value = ["broken", "ok"]
    ok_model, _, _ = _make_model_mock()
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
    status.offers = {}
    status.applications = {}
    model.get_status = AsyncMock(return_value=status)
    model.applications = {}
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
    status.offers = {}
    status.applications = {}
    model.get_status = AsyncMock(return_value=status)
    model.applications = {}
    mock_controller.get_model.return_value = model

    client = JujuClient()
    result = await client.get_relations("dev")

    assert len(result) == 1
    assert result[0].provider == "etcd:cluster"
    assert result[0].requirer == "etcd:cluster"
    assert result[0].type == "peer"


@pytest.mark.asyncio
async def test_get_relations_raises_on_failure(mock_controller):
    mock_controller.get_model.side_effect = Exception("boom")

    client = JujuClient()
    with pytest.raises(Exception, match="boom"):
        await client.get_relations("broken-model")


@pytest.mark.asyncio
async def test_get_status_details_returns_offers(mock_controller):
    from jujumate.models.entities import OfferInfo

    model = AsyncMock()
    status = MagicMock()
    status.relations = []
    app_st = MagicMock()
    app_st.charm_rev = 180
    status.applications = {"alertmanager": app_st}
    offer_st = MagicMock()
    offer_st.application_name = "alertmanager"
    offer_st.active_connected_count = 0
    offer_st.total_connected_count = 0
    ep = MagicMock()
    ep.interface = "karma_dashboard"
    ep.role = "provider"
    offer_st.endpoints = {"karma-dashboard": ep}
    status.offers = {"alertmanager-karma-dashboard": offer_st}
    status.application_endpoints = {}
    live_app = MagicMock()
    live_app.charm_name = "alertmanager-k8s"
    model.get_status = AsyncMock(return_value=status)
    model.applications = {"alertmanager": live_app}
    mock_controller.get_model.return_value = model

    client = JujuClient()
    relations, offers, saas = await client.get_status_details("cos")

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
async def test_get_secrets(mock_controller):
    from jujumate.models.entities import SecretInfo

    model = AsyncMock()
    model.name = "dev"
    mock_secret = MagicMock()
    mock_secret.uri = "csec:abc123"
    mock_secret.label = "my-secret"
    mock_secret.owner_tag = "model-dev"
    mock_secret.latest_revision = 2
    mock_secret.create_time = "2024-01-01T00:00:00"
    model.list_secrets = AsyncMock(return_value=[mock_secret])
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_secrets("dev")

    assert len(result) == 1
    assert isinstance(result[0], SecretInfo)
    assert result[0].uri == "csec:abc123"
    assert result[0].label == "my-secret"
    assert result[0].owner == "dev"
    assert result[0].revision == 2


@pytest.mark.asyncio
async def test_get_secrets_empty(mock_controller):
    model = AsyncMock()
    model.name = "dev"
    model.list_secrets = AsyncMock(return_value=[])
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_secrets("dev")
    assert result == []


@pytest.mark.asyncio
async def test_get_secrets_owner_without_dash(mock_controller):
    from jujumate.models.entities import SecretInfo

    model = AsyncMock()
    model.name = "dev"
    mock_secret = MagicMock()
    mock_secret.uri = "csec:xyz"
    mock_secret.label = "no-label"
    mock_secret.owner_tag = "modelonly"
    mock_secret.latest_revision = 1
    mock_secret.create_time = "2024-01-01"
    model.list_secrets = AsyncMock(return_value=[mock_secret])
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_secrets("dev")
    assert result[0].owner == "modelonly"


# ─────────────────────────────────────────────────────────────────────────────
# get_app_config
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_app_config(mock_controller):
    from jujumate.models.entities import AppConfigEntry

    model = AsyncMock()
    app_obj = AsyncMock()
    app_obj.get_config = AsyncMock(return_value={
        "log-level": {"value": "DEBUG", "default": "INFO", "type": "string", "description": "Level", "source": "user"},
        "port": {"value": 5432, "default": 5432, "type": "int", "description": "Port", "source": "default"},
    })
    model.applications = {"pg": app_obj}
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_app_config("dev", "pg")

    assert len(result) == 2
    assert all(isinstance(e, AppConfigEntry) for e in result)
    keys = {e.key for e in result}
    assert keys == {"log-level", "port"}


@pytest.mark.asyncio
async def test_get_app_config_non_dict_values_skipped(mock_controller):
    model = AsyncMock()
    app_obj = AsyncMock()
    app_obj.get_config = AsyncMock(return_value={
        "good": {"value": "v", "default": "d", "type": "string", "description": "desc", "source": "user"},
        "bad": "not-a-dict",
    })
    model.applications = {"pg": app_obj}
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_app_config("dev", "pg")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_app_config_app_not_found(mock_controller):
    model = AsyncMock()
    model.applications = {}
    mock_controller.get_model = AsyncMock(return_value=model)
    mock_controller.disconnect = AsyncMock()
    model.disconnect = AsyncMock()

    client = JujuClient()
    await client.connect()
    result = await client.get_app_config("dev", "missing")
    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# get_relation_data
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_relation_data_provider_side(mock_controller):
    from jujumate.models.entities import RelationDataEntry

    model = AsyncMock()
    model.connection = MagicMock(return_value=MagicMock())

    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    app_mock = MagicMock()
    app_mock.units = [unit_mock]
    wp_mock = MagicMock()
    wp_mock.units = []
    model.applications = {"postgresql": app_mock, "wordpress": wp_mock}

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

        mock_controller.get_model = AsyncMock(return_value=model)
        mock_controller.disconnect = AsyncMock()
        model.disconnect = AsyncMock()

        client = JujuClient()
        await client.connect()
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")

    assert len(result) > 0
    assert all(isinstance(e, RelationDataEntry) for e in result)


@pytest.mark.asyncio
async def test_get_relation_data_no_units(mock_controller):
    model = AsyncMock()
    model.connection = MagicMock(return_value=MagicMock())

    app_mock = MagicMock()
    app_mock.units = []
    model.applications = {"postgresql": app_mock, "wordpress": MagicMock(units=[])}

    with patch("juju.client.client.ApplicationFacade") as MockFacade:
        facade_inst = AsyncMock()
        MockFacade.from_connection = MagicMock(return_value=facade_inst)
        facade_inst.UnitsInfo = AsyncMock(return_value=MagicMock(results=[]))
        mock_controller.get_model = AsyncMock(return_value=model)
        mock_controller.disconnect = AsyncMock()
        model.disconnect = AsyncMock()

        client = JujuClient()
        await client.connect()
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")

    assert result == []


@pytest.mark.asyncio
async def test_get_relation_data_skips_wrong_relation_id(mock_controller):
    model = AsyncMock()
    model.connection = MagicMock(return_value=MagicMock())

    unit_mock = MagicMock()
    unit_mock.name = "pg/0"
    app_mock = MagicMock()
    app_mock.units = [unit_mock]
    model.applications = {"postgresql": app_mock}

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

        mock_controller.get_model = AsyncMock(return_value=model)
        mock_controller.disconnect = AsyncMock()
        model.disconnect = AsyncMock()

        client = JujuClient()
        await client.connect()
        result = await client.get_relation_data("dev", 5, "postgresql", "wordpress")

    assert result == []
