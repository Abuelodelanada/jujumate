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
    """Fetches Juju data periodically and posts Textual messages to a widget."""

    def __init__(self, client: JujuClient, target: Widget) -> None:
        self._client = client
        self._target = target

    async def poll_once(self) -> None:
        """Fetch all data and post update messages."""
        logger.info("Polling Juju data")
        try:
            clouds = await self._client.get_clouds()
            self._target.post_message(CloudsUpdated(clouds=clouds))

            models = await self._client.get_models()
            self._target.post_message(ModelsUpdated(models=models))

            all_apps: list[AppInfo] = []
            all_units: list[UnitInfo] = []
            for model in models:
                all_apps.extend(await self._client.get_applications(model.name))
                all_units.extend(await self._client.get_units(model.name))

            self._target.post_message(AppsUpdated(apps=all_apps))
            self._target.post_message(UnitsUpdated(units=all_units))
            self._target.post_message(DataRefreshed())
            logger.info("Poll complete")
        except Exception as e:
            logger.exception("Poll failed")
            self._target.post_message(ConnectionFailed(error=str(e)))
