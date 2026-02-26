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
class RelationInfo:
    model: str
    provider: str
    requirer: str
    interface: str
    type: str


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
