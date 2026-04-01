import asyncio
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
    model: str = ""
    controller: str = ""


@dataclass
class AppsUpdated(JujuDataMessage):
    apps: list[AppInfo] = field(default_factory=list)
    model: str = ""
    controller: str = ""


@dataclass
class UnitsUpdated(JujuDataMessage):
    units: list[UnitInfo] = field(default_factory=list)
    model: str = ""
    controller: str = ""


@dataclass
class MachinesUpdated(JujuDataMessage):
    machines: list[MachineInfo] = field(default_factory=list)
    model: str = ""
    controller: str = ""


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
    relations: dict[tuple[str, str], list[RelationInfo]] = field(default_factory=dict)
    offers: dict[tuple[str, str], list[OfferInfo]] = field(default_factory=dict)
    saas: dict[tuple[str, str], list[SAASInfo]] = field(default_factory=dict)
    failed: int = 0


async def _poll_controller(name: str, snapshot: PollSnapshot) -> None:
    """Fetch data from one controller and merge results into *snapshot*."""
    async with JujuClient(controller_name=name) as client:
        for cloud in await client.get_clouds():
            snapshot.clouds[cloud.name] = cloud
        model_names = await client.list_model_names()
        for ctrl in await client.get_controllers(model_names=model_names):
            snapshot.controllers[ctrl.name] = ctrl
        for model_name in model_names:
            (
                model_info,
                apps,
                units,
                machines,
                relations,
                offers,
                saas,
            ) = await client.get_model_snapshot(model_name)
            key = (model_info.controller, model_info.name)
            snapshot.models[key] = model_info
            for app in apps:
                snapshot.apps[(app.controller, app.model, app.name)] = app
            for unit in units:
                snapshot.units[(unit.controller, unit.model, unit.app, unit.name)] = unit
            for machine in machines:
                snapshot.machines[(machine.controller, model_name, machine.id)] = machine
            snapshot.relations[key] = relations
            snapshot.offers[key] = offers
            snapshot.saas[key] = saas


def _post_snapshot_messages(target: Widget, snapshot: PollSnapshot) -> None:
    """Post aggregated update messages to *target* from a completed snapshot."""
    target.post_message(CloudsUpdated(clouds=list(snapshot.clouds.values())))
    target.post_message(ControllersUpdated(controllers=list(snapshot.controllers.values())))
    target.post_message(ModelsUpdated(models=list(snapshot.models.values())))
    target.post_message(AppsUpdated(apps=list(snapshot.apps.values())))
    target.post_message(UnitsUpdated(units=list(snapshot.units.values())))
    target.post_message(MachinesUpdated(machines=list(snapshot.machines.values())))
    for (controller, model), relations in snapshot.relations.items():
        target.post_message(
            RelationsUpdated(model=model, controller=controller, relations=relations)
        )
    for (controller, model), offers in snapshot.offers.items():
        target.post_message(OffersUpdated(model=model, controller=controller, offers=offers))
    for (controller, model), saas in snapshot.saas.items():
        target.post_message(SaasUpdated(model=model, controller=controller, saas=saas))
    target.post_message(DataRefreshed())


# ── Poller ────────────────────────────────────────────────────────────────────


class JujuPoller:
    """Fetches data from all known controllers and posts Textual messages."""

    def __init__(self, controller_names: list[str], target: Widget) -> None:
        self._controller_names = controller_names
        self._target = target

    async def poll_once(self) -> None:
        """Fetch data from all controllers concurrently and post aggregated update messages."""
        logger.debug("Polling %d controller(s)", len(self._controller_names))
        if not self._controller_names:
            self._target.post_message(ConnectionFailed(error="No controllers configured"))
            return

        snapshot = PollSnapshot()

        async def _poll_safe(name: str) -> None:
            try:
                await _poll_controller(name, snapshot)
            except Exception:
                logger.exception("Failed to poll controller '%s'", name)
                snapshot.failed += 1

        await asyncio.gather(*(_poll_safe(name) for name in self._controller_names))

        if snapshot.failed == len(self._controller_names):
            self._target.post_message(ConnectionFailed(error="All controllers failed to connect"))
            return

        _post_snapshot_messages(self._target, snapshot)
        logger.debug(
            "Poll complete: %d controller(s) OK, %d failed",
            len(self._controller_names) - snapshot.failed,
            snapshot.failed,
        )

    async def poll_model(self, controller_name: str, model_name: str) -> None:
        """Fetch fresh data for a single model and post targeted update messages.

        Used when the Status tab is active with a specific model selected.
        Reduces cost from O(3C + M) to O(1) — one controller connection, one model.
        Clouds, controllers list and models list are NOT refreshed (they rarely change).
        """
        logger.debug("Targeted poll: controller='%s' model='%s'", controller_name, model_name)
        try:
            async with JujuClient(controller_name=controller_name) as client:
                (
                    model_info,
                    apps,
                    units,
                    machines,
                    relations,
                    offers,
                    saas,
                ) = await client.get_model_snapshot(model_name)
        except Exception:
            logger.exception(
                "Failed targeted poll for model '%s' on controller '%s'",
                model_name,
                controller_name,
            )
            self._target.post_message(
                ConnectionFailed(error=f"Failed to refresh model '{model_name}'")
            )
            return

        self._target.post_message(
            ModelsUpdated(models=[model_info], model=model_name, controller=controller_name)
        )
        self._target.post_message(
            AppsUpdated(apps=apps, model=model_name, controller=controller_name)
        )
        self._target.post_message(
            UnitsUpdated(units=units, model=model_name, controller=controller_name)
        )
        self._target.post_message(
            MachinesUpdated(machines=machines, model=model_name, controller=controller_name)
        )
        self._target.post_message(
            RelationsUpdated(model=model_name, controller=controller_name, relations=relations)
        )
        self._target.post_message(
            OffersUpdated(model=model_name, controller=controller_name, offers=offers)
        )
        self._target.post_message(
            SaasUpdated(model=model_name, controller=controller_name, saas=saas)
        )
        self._target.post_message(DataRefreshed())
        logger.debug(
            "Targeted poll complete: %d apps, %d units, %d machines",
            len(apps),
            len(units),
            len(machines),
        )
