import logging
from dataclasses import dataclass, field
from datetime import datetime

from textual.message import Message
from textual.widget import Widget

from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    MachineInfo,
    ModelInfo,
    OfferInfo,
    RelationDataEntry,
    RelationInfo,
    SAASInfo,
    UnitInfo,
)

logger = logging.getLogger(__name__)


# ── Textual messages ──────────────────────────────────────────────────────────


class JujuDataMessage(Message):
    """Base class for all Juju data update messages."""


@dataclass
class CloudsUpdated(JujuDataMessage):
    clouds: list[CloudInfo] = field(default_factory=list)


@dataclass
class ControllersUpdated(JujuDataMessage):
    controllers: list[ControllerInfo] = field(default_factory=list)


@dataclass
class ModelsUpdated(JujuDataMessage):
    models: list[ModelInfo] = field(default_factory=list)


@dataclass
class AppsUpdated(JujuDataMessage):
    apps: list[AppInfo] = field(default_factory=list)


@dataclass
class UnitsUpdated(JujuDataMessage):
    units: list[UnitInfo] = field(default_factory=list)


@dataclass
class MachinesUpdated(JujuDataMessage):
    machines: list[MachineInfo] = field(default_factory=list)


@dataclass
class RelationsUpdated(JujuDataMessage):
    model: str = ""
    controller: str = ""
    relations: list[RelationInfo] = field(default_factory=list)


@dataclass
class OffersUpdated(JujuDataMessage):
    model: str = ""
    controller: str = ""
    offers: list[OfferInfo] = field(default_factory=list)


@dataclass
class SaasUpdated(JujuDataMessage):
    model: str = ""
    controller: str = ""
    saas: list[SAASInfo] = field(default_factory=list)


@dataclass
class DataRefreshed(JujuDataMessage):
    """Posted after a full refresh cycle completes."""

    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RelationDataUpdated(JujuDataMessage):
    """Posted when relation data bags have been fetched."""

    relation: RelationInfo = field(default_factory=lambda: RelationInfo("", "", "", "", ""))
    entries: list[RelationDataEntry] = field(default_factory=list)


@dataclass
class RelationDataFetchError(JujuDataMessage):
    """Posted when fetching relation data bags failed."""

    relation: RelationInfo = field(default_factory=lambda: RelationInfo("", "", "", "", ""))
    error: str = ""


@dataclass
class AppConfigFetched(JujuDataMessage):
    """Posted when app configuration has been fetched."""

    app: AppInfo = field(default_factory=lambda: AppInfo("", "", "", "", 0))
    entries: list[AppConfigEntry] = field(default_factory=list)


@dataclass
class AppConfigFetchError(JujuDataMessage):
    """Posted when fetching app configuration failed."""

    app: AppInfo = field(default_factory=lambda: AppInfo("", "", "", "", 0))
    error: str = ""


@dataclass
class ConnectionFailed(JujuDataMessage):
    error: str = ""


# ── Poll helpers ──────────────────────────────────────────────────────────────


@dataclass
class PollSnapshot:
    clouds: dict[str, CloudInfo] = field(default_factory=dict)
    controllers: dict[str, ControllerInfo] = field(default_factory=dict)
    models: dict[tuple[str, str], ModelInfo] = field(default_factory=dict)
    apps: dict[tuple[str, str, str], AppInfo] = field(default_factory=dict)
    units: dict[tuple[str, str, str, str], UnitInfo] = field(default_factory=dict)
    machines: dict[tuple[str, str, str], MachineInfo] = field(default_factory=dict)
    failed: int = 0


async def _poll_controller(name: str, snapshot: PollSnapshot) -> None:
    """Fetch data from one controller and merge results into *snapshot*."""
    async with JujuClient(controller_name=name) as client:
        for cloud in await client.get_clouds():
            snapshot.clouds[cloud.name] = cloud
        for ctrl in await client.get_controllers():
            snapshot.controllers[ctrl.name] = ctrl
        for model_name in await client.list_model_names():
            model_info, apps, units, machines = await client.get_model_snapshot(model_name)
            snapshot.models[(model_info.controller, model_info.name)] = model_info
            for app in apps:
                snapshot.apps[(app.controller, app.model, app.name)] = app
            for unit in units:
                snapshot.units[(unit.controller, unit.model, unit.app, unit.name)] = unit
            for machine in machines:
                snapshot.machines[(machine.controller, model_name, machine.id)] = machine


def _post_snapshot_messages(target: Widget, snapshot: PollSnapshot) -> None:
    """Post aggregated update messages to *target* from a completed snapshot."""
    target.post_message(CloudsUpdated(clouds=list(snapshot.clouds.values())))
    target.post_message(ControllersUpdated(controllers=list(snapshot.controllers.values())))
    target.post_message(ModelsUpdated(models=list(snapshot.models.values())))
    target.post_message(AppsUpdated(apps=list(snapshot.apps.values())))
    target.post_message(UnitsUpdated(units=list(snapshot.units.values())))
    target.post_message(MachinesUpdated(machines=list(snapshot.machines.values())))
    target.post_message(DataRefreshed())


# ── Poller ────────────────────────────────────────────────────────────────────


class JujuPoller:
    """Fetches data from all known controllers and posts Textual messages."""

    def __init__(self, controller_names: list[str], target: Widget) -> None:
        self._controller_names = controller_names
        self._target = target

    async def poll_once(self) -> None:
        """Fetch data from every controller and post aggregated update messages."""
        logger.debug("Polling %d controller(s)", len(self._controller_names))
        if not self._controller_names:
            self._target.post_message(ConnectionFailed(error="No controllers configured"))
            return

        snapshot = PollSnapshot()
        for name in self._controller_names:
            try:
                await _poll_controller(name, snapshot)
            except Exception:
                logger.exception("Failed to poll controller '%s'", name)
                snapshot.failed += 1

        if snapshot.failed == len(self._controller_names):
            self._target.post_message(ConnectionFailed(error="All controllers failed to connect"))
            return

        _post_snapshot_messages(self._target, snapshot)
        logger.debug(
            "Poll complete: %d controller(s) OK, %d failed",
            len(self._controller_names) - snapshot.failed,
            snapshot.failed,
        )
