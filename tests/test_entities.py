import pytest

from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    ControllerOfferInfo,
    LogEntry,
    MachineInfo,
    ModelInfo,
    OfferEndpoint,
    OfferInfo,
    RelationDataEntry,
    RelationInfo,
    SAASInfo,
    SecretInfo,
    UnitInfo,
)


def test_cloud_info_defaults():
    # GIVEN only required fields
    # WHEN creating a CloudInfo
    cloud = CloudInfo(name="aws", type="ec2")
    # THEN optional lists default to empty
    assert cloud.regions == []
    assert cloud.credentials == []


def test_cloud_info_full():
    # GIVEN all fields provided
    # WHEN creating a CloudInfo
    cloud = CloudInfo(name="aws", type="ec2", regions=["us-east-1"], credentials=["admin"])
    # THEN all values are stored correctly
    assert cloud.name == "aws"
    assert cloud.regions == ["us-east-1"]


def test_controller_info():
    # GIVEN only required fields
    # WHEN creating a ControllerInfo
    ctrl = ControllerInfo(name="prod", cloud="aws", region="us-east-1", juju_version="3.6.0")
    # THEN model_count defaults to zero
    assert ctrl.model_count == 0


def test_model_info_defaults():
    # GIVEN only required fields
    # WHEN creating a ModelInfo
    model = ModelInfo(
        name="dev", controller="prod", cloud="aws", region="us-east-1", status="available"
    )
    # THEN numeric counters default to zero
    assert model.machine_count == 0
    assert model.app_count == 0


def test_app_info_defaults():
    # GIVEN only required fields
    # WHEN creating an AppInfo
    app = AppInfo(
        name="postgresql", model="dev", charm="postgresql", channel="14/stable", revision=363
    )
    # THEN optional fields default to empty
    assert app.unit_count == 0
    assert app.status == ""
    assert app.message == ""


def test_unit_info_defaults():
    # GIVEN only required fields
    # WHEN creating a UnitInfo
    unit = UnitInfo(
        name="postgresql/0",
        app="postgresql",
        machine="0",
        workload_status="active",
        agent_status="idle",
    )
    # THEN optional address defaults to empty string
    assert unit.address == ""


def test_unit_info_full():
    # GIVEN all fields provided
    # WHEN creating a UnitInfo
    unit = UnitInfo(
        name="mysql/0",
        app="mysql",
        machine="1",
        workload_status="active",
        agent_status="idle",
        address="10.0.0.1",
        public_address="1.2.3.4",
        ports="3306/tcp",
        message="ready",
        subordinate_of="",
        model="dev",
        controller="prod",
    )
    # THEN all provided values are stored correctly
    assert unit.ports == "3306/tcp"
    assert unit.model == "dev"
    assert unit.subordinate_of == ""


def test_saas_info_defaults():
    # GIVEN only required fields
    # WHEN creating a SAASInfo
    saas = SAASInfo(model="dev", name="db", status="active", store="localhost", url="admin/dev.db")
    # THEN controller defaults to empty string and required fields are stored
    assert saas.controller == ""
    assert saas.store == "localhost"


def test_offer_endpoint():
    # GIVEN name, interface and role
    # WHEN creating an OfferEndpoint
    ep = OfferEndpoint(name="db", interface="pgsql", role="provider")
    # THEN all fields are stored correctly
    assert ep.name == "db"
    assert ep.role == "provider"


def test_controller_offer_info_defaults():
    # GIVEN only required fields
    # WHEN creating a ControllerOfferInfo
    offer = ControllerOfferInfo(
        model="dev",
        name="pg-offer",
        offer_url="admin/dev.pg-offer",
        application="postgresql",
        charm="ch:postgresql",
        description="PostgreSQL offer",
    )
    # THEN optional fields default to empty/zero
    assert offer.access == ""
    assert offer.endpoints == []
    assert offer.active_connections == 0
    assert offer.total_connections == 0


def test_controller_offer_info_with_endpoints():
    # GIVEN an endpoint and connection counts
    ep = OfferEndpoint(name="db", interface="pgsql", role="provider")
    # WHEN creating a ControllerOfferInfo with all fields
    offer = ControllerOfferInfo(
        model="dev",
        name="pg-offer",
        offer_url="admin/dev.pg-offer",
        application="postgresql",
        charm="ch:postgresql",
        description="PostgreSQL offer",
        access="admin",
        endpoints=[ep],
        active_connections=2,
        total_connections=3,
    )
    # THEN endpoints list and connection counts are stored correctly
    assert len(offer.endpoints) == 1
    assert offer.endpoints[0].interface == "pgsql"
    assert offer.active_connections == 2


def test_offer_info_defaults():
    # GIVEN only required fields
    # WHEN creating an OfferInfo
    offer = OfferInfo(
        model="dev",
        name="pg-offer",
        application="postgresql",
        charm="ch:postgresql",
        rev=363,
        connected="1/1",
        endpoint="db",
        interface="pgsql",
        role="provider",
    )
    # THEN controller defaults to empty and rev is stored correctly
    assert offer.controller == ""
    assert offer.rev == 363


def test_relation_info_defaults():
    # GIVEN only required fields
    # WHEN creating a RelationInfo
    rel = RelationInfo(
        model="dev",
        provider="postgresql:db",
        requirer="myapp:db",
        interface="pgsql",
        type="regular",
    )
    # THEN relation_id and controller default to zero/empty
    assert rel.relation_id == 0
    assert rel.controller == ""


def test_relation_info_full():
    # GIVEN all fields including relation_id and controller
    # WHEN creating a RelationInfo
    rel = RelationInfo(
        model="dev",
        provider="postgresql:db",
        requirer="myapp:db",
        interface="pgsql",
        type="regular",
        relation_id=42,
        controller="prod",
    )
    # THEN all values are stored correctly
    assert rel.relation_id == 42
    assert rel.controller == "prod"


@pytest.mark.parametrize(
    "kwargs, expected_scope",
    [
        ({"side": "provider", "unit": "postgresql/0", "key": "host", "value": "10.0.0.1"}, "unit"),
        (
            {
                "side": "requirer",
                "unit": "myapp",
                "key": "password",
                "value": "secret",
                "scope": "app",
            },
            "app",
        ),
    ],
    ids=["default-unit-scope", "explicit-app-scope"],
)
def test_relation_data_entry_scope(kwargs: dict, expected_scope: str) -> None:
    # GIVEN a RelationDataEntry with the provided kwargs
    # WHEN creating the entry
    entry = RelationDataEntry(**kwargs)
    # THEN the scope matches the expected value
    assert entry.scope == expected_scope


@pytest.mark.parametrize(
    "source, expected",
    [
        ("default", True),
        ("user", False),
    ],
    ids=["source-default", "source-user"],
)
def test_app_config_entry_is_default(source: str, expected: bool) -> None:
    # GIVEN an AppConfigEntry with the given source
    # WHEN creating the entry
    cfg = AppConfigEntry(
        key="log-level",
        value="INFO",
        default="INFO",
        type="string",
        description="Log level",
        source=source,
    )
    # THEN is_default reflects whether the source is "default"
    assert cfg.is_default is expected


def test_machine_info_defaults():
    # GIVEN only required fields
    # WHEN creating a MachineInfo
    machine = MachineInfo(
        model="dev",
        id="0",
        state="started",
        address="10.0.0.1",
        instance_id="i-0abc123",
        base="ubuntu@22.04",
        az="us-east-1a",
    )
    # THEN message and controller default to empty string
    assert machine.message == ""
    assert machine.controller == ""


def test_machine_info_full():
    # GIVEN all fields including message and controller
    # WHEN creating a MachineInfo
    machine = MachineInfo(
        model="dev",
        id="1",
        state="started",
        address="10.0.0.2",
        instance_id="i-0def456",
        base="ubuntu@22.04",
        az="us-east-1b",
        message="running",
        controller="prod",
    )
    # THEN all provided values are stored correctly
    assert machine.message == "running"
    assert machine.controller == "prod"


def test_secret_info():
    # GIVEN all required fields
    # WHEN creating a SecretInfo
    secret = SecretInfo(
        uri="secret:abc123",
        label="my-secret",
        owner="myapp",
        description="A test secret",
        revision=3,
        rotate_policy="never",
        created="2024-01-01T00:00:00Z",
        updated="2024-06-01T00:00:00Z",
    )
    # THEN all fields are stored correctly
    assert secret.revision == 3
    assert secret.rotate_policy == "never"


def test_log_entry():
    # GIVEN all required fields
    # WHEN creating a LogEntry
    entry = LogEntry(
        timestamp="2024-01-01T00:00:00Z",
        level="INFO",
        entity="unit:mysql/0",
        module="juju.worker",
        message="started",
    )
    # THEN all fields are stored correctly
    assert entry.level == "INFO"
    assert entry.entity == "unit:mysql/0"
