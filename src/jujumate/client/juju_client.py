import logging

from juju.controller import Controller

from jujumate.models.entities import AppInfo, CloudInfo, ModelInfo, UnitInfo

logger = logging.getLogger(__name__)


class JujuClientError(Exception):
    pass


class JujuClient:
    def __init__(self, controller_name: str | None = None) -> None:
        self._controller_name = controller_name
        self._controller = Controller()

    async def connect(self) -> None:
        logger.info("Connecting to controller: %s", self._controller_name or "current")
        try:
            if self._controller_name:
                await self._controller.connect(self._controller_name)
            else:
                await self._controller.connect_current()
        except Exception as e:
            raise JujuClientError(f"Failed to connect to controller: {e}") from e
        logger.info("Connected to controller: %s", self._controller.controller_name)

    async def disconnect(self) -> None:
        logger.info("Disconnecting from controller")
        await self._controller.disconnect()

    async def __aenter__(self) -> "JujuClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def get_clouds(self) -> list[CloudInfo]:
        result = await self._controller.clouds()
        clouds = []
        for tag, cloud in result.clouds.items():
            name = tag.split("-", 1)[-1] if "-" in tag else tag
            regions = [r.name for r in (cloud.regions or [])]
            clouds.append(CloudInfo(name=name, type=cloud.type_, regions=regions))
        logger.debug("Fetched %d clouds", len(clouds))
        return clouds

    async def get_models(self) -> list[ModelInfo]:
        model_names = await self._controller.list_models()
        models = []
        for name in model_names:
            try:
                info = await self._controller.get_model_info(model_name=name)
                cloud_tag = info.cloud_tag or ""
                cloud = cloud_tag.split("-", 1)[-1] if "-" in cloud_tag else cloud_tag
                models.append(
                    ModelInfo(
                        name=name,
                        controller=self._controller.controller_name or "",
                        cloud=cloud,
                        region=info.cloud_region or "",
                        status=info.status.current if info.status else "",
                        machine_count=len(info.machines) if info.machines else 0,
                        app_count=len(info.applications) if info.applications else 0,
                    )
                )
            except Exception:
                logger.exception("Failed to get info for model '%s'", name)
        logger.debug("Fetched %d models", len(models))
        return models

    async def get_applications(self, model_name: str) -> list[AppInfo]:
        apps = []
        try:
            model = await self._controller.get_model(model_name)
            for app in model.applications.values():
                apps.append(
                    AppInfo(
                        name=app.name,
                        model=model_name,
                        charm=app.charm_name,
                        channel=app.data.get("charm-channel", ""),
                        revision=int(app.data.get("charm-rev", 0)),
                        unit_count=len(app.units),
                        status=app.status,
                        message=app.status_message,
                    )
                )
            await model.disconnect()
        except Exception:
            logger.exception("Failed to get applications for model '%s'", model_name)
        logger.debug("Fetched %d applications for model '%s'", len(apps), model_name)
        return apps

    async def get_units(self, model_name: str) -> list[UnitInfo]:
        units = []
        try:
            model = await self._controller.get_model(model_name)
            for unit in model.units.values():
                units.append(
                    UnitInfo(
                        name=unit.name,
                        app=unit.application,
                        machine=unit.machine_id or "",
                        workload_status=unit.workload_status,
                        agent_status=unit.agent_status,
                        address=unit.public_address or "",
                    )
                )
            await model.disconnect()
        except Exception:
            logger.exception("Failed to get units for model '%s'", model_name)
        logger.debug("Fetched %d units for model '%s'", len(units), model_name)
        return units
