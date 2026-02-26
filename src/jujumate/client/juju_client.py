import logging

from juju.controller import Controller

from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo

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

    async def get_controllers(self) -> list[ControllerInfo]:
        try:
            cloud_name = await self._controller.get_cloud()
            conn = self._controller.connection()
            info: dict = conn.info if isinstance(conn.info, dict) else {}
            juju_version = str(info.get("server-version", ""))
            model_names = await self._controller.list_models()
            controllers = [
                ControllerInfo(
                    name=self._controller.controller_name or "",
                    cloud=cloud_name,
                    region="",
                    juju_version=juju_version,
                    model_count=len(model_names),
                )
            ]
        except Exception:
            logger.exception("Failed to get controller info")
            controllers = []
        logger.debug("Fetched %d controllers", len(controllers))
        return controllers

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
        controller_name = self._controller.controller_name or ""
        logger.debug("Listing models for controller '%s': %s", controller_name, model_names)
        models = []
        for name in model_names:
            try:
                model = await self._controller.get_model(name)
                info = model.info
                cloud_tag = (info.cloud_tag or "") if info else ""
                cloud = cloud_tag.split("-", 1)[-1] if "-" in cloud_tag else cloud_tag
                models.append(
                    ModelInfo(
                        name=name,
                        controller=controller_name,
                        cloud=cloud,
                        region=(info.cloud_region or "") if info else "",
                        status=info.status.status if info and info.status else "",
                        machine_count=len(model.machines),
                        app_count=len(model.applications),
                    )
                )
                await model.disconnect()
            except Exception:
                logger.exception("Failed to get full info for model '%s', using minimal info", name)
                models.append(
                    ModelInfo(
                        name=name,
                        controller=controller_name,
                        cloud="",
                        region="",
                        status="unknown",
                    )
                )
        logger.debug("Fetched %d models for controller '%s'", len(models), controller_name)
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
