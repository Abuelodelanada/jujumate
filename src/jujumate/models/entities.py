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
    can_upgrade_to: str = ""
    controller: str = ""


@dataclass
class SAASInfo:
    model: str
    name: str
    status: str
    store: str
    url: str
    controller: str = ""


@dataclass
class OfferEndpoint:
    """An endpoint exposed by a controller-level offer."""

    name: str
    interface: str
    role: str


@dataclass
class ControllerOfferInfo:
    """Rich offer info fetched controller-wide (all models)."""

    model: str
    name: str
    offer_url: str
    application: str
    charm: str
    description: str
    access: str = ""
    endpoints: list[OfferEndpoint] = field(default_factory=list)
    active_connections: int = 0
    total_connections: int = 0


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
    controller: str = ""


@dataclass
class RelationInfo:
    model: str
    provider: str
    requirer: str
    interface: str
    type: str
    relation_id: int = 0
    controller: str = ""


@dataclass
class RelationDataEntry:
    """A single key-value entry from a relation data bag."""

    side: str  # "provider", "requirer", or "peer"
    unit: str  # unit name or app name
    key: str
    value: str
    scope: str = "unit"  # "app" or "unit"


@dataclass
class AppConfigEntry:
    """A single config entry for an application."""

    key: str
    value: str
    default: str
    type: str
    description: str
    source: str  # "default" or "user"

    @property
    def is_default(self) -> bool:
        return self.source == "default"


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
    is_leader: bool = False
    subordinate_of: str = ""  # principal unit name, empty if this is a principal
    model: str = ""
    controller: str = ""


@dataclass
class NetworkInterface:
    name: str
    ips: list[str]
    mac: str
    space: str = ""


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
    controller: str = ""
    # Extended fields — populated for the detail modal
    hardware_arch: str = ""
    hardware_cores: int = 0
    hardware_mem_mib: int = 0
    hardware_disk_mib: int = 0
    hardware_virt_type: str = ""
    agent_since: str = ""
    instance_status: str = ""
    instance_since: str = ""
    network_interfaces: list[NetworkInterface] = field(default_factory=list)


@dataclass
class SecretInfo:
    uri: str
    label: str
    owner: str
    description: str
    revision: int
    rotate_policy: str
    created: str
    updated: str


@dataclass
class LogEntry:
    timestamp: str
    level: str  # TRACE | DEBUG | INFO | WARNING | ERROR
    entity: str  # e.g. "unit:mysql/0", "machine:2"
    module: str
    message: str
