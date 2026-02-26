import logging
from dataclasses import dataclass, field
from datetime import datetime

from textual.message import Message
from textual.widget import Widget

from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo

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
class DataRefreshed(JujuDataMessage):
    """Posted after a full refresh cycle completes."""

    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConnectionFailed(JujuDataMessage):
    error: str = ""


# ── Poller ────────────────────────────────────────────────────────────────────


class JujuPoller:
    """Fetches data from all known controllers and posts Textual messages."""

    def __init__(self, controller_names: list[str], target: Widget) -> None:
        self._controller_names = controller_names
        self._target = target

    async def poll_once(self) -> None:
        """Fetch data from every controller and post aggregated update messages."""
        logger.info("Polling %d controller(s)", len(self._controller_names))

        if not self._controller_names:
            self._target.post_message(ConnectionFailed(error="No controllers configured"))
            return

        all_clouds: dict[str, CloudInfo] = {}  # dedup by cloud name
        all_controllers: dict[str, ControllerInfo] = {}  # dedup by controller name
        all_models: dict[tuple[str, str], ModelInfo] = {}  # dedup by (controller, model)
        all_apps: dict[tuple[str, str], AppInfo] = {}  # dedup by (model, app)
        all_units: dict[tuple[str, str], UnitInfo] = {}  # dedup by (app, unit)
        failed = 0

        for name in self._controller_names:
            try:
                async with JujuClient(controller_name=name) as client:
                    for cloud in await client.get_clouds():
                        all_clouds[cloud.name] = cloud
                    for ctrl in await client.get_controllers():
                        all_controllers[ctrl.name] = ctrl
                    models = await client.get_models()
                    for model in models:
                        all_models[(model.controller, model.name)] = model
                        for app in await client.get_applications(model.name):
                            all_apps[(app.model, app.name)] = app
                        for unit in await client.get_units(model.name):
                            all_units[(unit.app, unit.name)] = unit
            except Exception:
                logger.exception("Failed to poll controller '%s'", name)
                failed += 1

        if failed == len(self._controller_names):
            self._target.post_message(ConnectionFailed(error="All controllers failed to connect"))
            return

        self._target.post_message(CloudsUpdated(clouds=list(all_clouds.values())))
        self._target.post_message(ControllersUpdated(controllers=list(all_controllers.values())))
        self._target.post_message(ModelsUpdated(models=list(all_models.values())))
        self._target.post_message(AppsUpdated(apps=list(all_apps.values())))
        self._target.post_message(UnitsUpdated(units=list(all_units.values())))
        self._target.post_message(DataRefreshed())
        logger.info(
            "Poll complete: %d controller(s) OK, %d failed",
            len(self._controller_names) - failed,
            failed,
        )
