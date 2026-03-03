from dataclasses import dataclass, field


@dataclass
class CloudInfo:
    name: str
    type: str
    regions: list[str] = field(default_factory=list)
    credentials: list[str] = field(default_factory=list)


@dataclass
class ControllerInfo:
    name: str
    cloud: str
    region: str
    juju_version: str
    model_count: int = 0


@dataclass
class ModelInfo:
    name: str
    controller: str
    cloud: str
    region: str
    status: str
    machine_count: int = 0
    app_count: int = 0
    is_kubernetes: bool = False


@dataclass
class AppInfo:
    name: str
    model: str
    charm: str
    channel: str
    revision: int
    unit_count: int = 0
    status: str = ""
    message: str = ""
    version: str = ""
    address: str = ""
    exposed: bool = False


@dataclass
class SAASInfo:
    model: str
    name: str
    status: str
    store: str
    url: str


@dataclass
class OfferInfo:
    model: str
    name: str
    application: str
    charm: str
    rev: int
    connected: str
    endpoint: str
    interface: str
    role: str


@dataclass
class RelationInfo:
    model: str
    provider: str
    requirer: str
    interface: str
    type: str
    relation_id: int = 0


@dataclass
class RelationDataEntry:
    """A single key-value entry from a relation data bag."""

    side: str   # "provider", "requirer", or "peer"
    unit: str   # unit name or app name
    key: str
    value: str
    scope: str = "unit"  # "app" or "unit"


@dataclass
class UnitInfo:
    name: str
    app: str
    machine: str
    workload_status: str
    agent_status: str
    address: str = ""
    public_address: str = ""
    ports: str = ""
    message: str = ""
    subordinate_of: str = ""  # principal unit name, empty if this is a principal
    model: str = ""


@dataclass
class MachineInfo:
    model: str
    id: str
    state: str
    address: str
    instance_id: str
    base: str
    az: str
    message: str = ""
