import logging

from juju.controller import Controller

from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, RelationInfo, UnitInfo

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

    async def list_model_names(self) -> list[str]:
        return await self._controller.list_models()

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

    async def get_model_snapshot(
        self, model_name: str
    ) -> tuple[ModelInfo, list[AppInfo], list[UnitInfo]]:
        """Fetch ModelInfo, AppInfo list, and UnitInfo list in a single model connection."""
        controller_name = self._controller.controller_name or ""
        try:
            model = await self._controller.get_model(model_name)
            try:
                info = model.info
                cloud_tag = (info.cloud_tag or "") if info else ""
                cloud = cloud_tag.split("-", 1)[-1] if "-" in cloud_tag else cloud_tag
                model_info = ModelInfo(
                    name=model_name,
                    controller=controller_name,
                    cloud=cloud,
                    region=(info.cloud_region or "") if info else "",
                    status=info.status.status if info and info.status else "",
                    machine_count=len(model.machines),
                    app_count=len(model.applications),
                )
                apps = [
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
                    for app in model.applications.values()
                ]
                units = [
                    UnitInfo(
                        name=unit.name,
                        app=unit.application,
                        machine=unit.machine_id or "",
                        workload_status=unit.workload_status,
                        agent_status=unit.agent_status,
                        address=unit.public_address or "",
                    )
                    for unit in model.units.values()
                ]
            finally:
                await model.disconnect()
        except Exception:
            logger.exception("Failed to get snapshot for model '%s', using minimal info", model_name)
            model_info = ModelInfo(
                name=model_name,
                controller=controller_name,
                cloud="",
                region="",
                status="unknown",
            )
            apps = []
            units = []
        logger.debug(
            "Snapshot for model '%s': %d apps, %d units", model_name, len(apps), len(units)
        )
        return model_info, apps, units

    async def get_models(self) -> list[ModelInfo]:
        model_names = await self._controller.list_models()
        controller_name = self._controller.controller_name or ""
        logger.debug("Listing models for controller '%s': %s", controller_name, model_names)
        models = []
        for name in model_names:
            model_info, _, _ = await self.get_model_snapshot(name)
            models.append(model_info)
        logger.debug("Fetched %d models for controller '%s'", len(models), controller_name)
        return models

    async def get_applications(self, model_name: str) -> list[AppInfo]:
        _, apps, _ = await self.get_model_snapshot(model_name)
        logger.debug("Fetched %d applications for model '%s'", len(apps), model_name)
        return apps

    async def get_units(self, model_name: str) -> list[UnitInfo]:
        _, _, units = await self.get_model_snapshot(model_name)
        logger.debug("Fetched %d units for model '%s'", len(units), model_name)
        return units

    async def get_relations(self, model_name: str) -> list[RelationInfo]:
        relations: list[RelationInfo] = []
        try:
            model = await self._controller.get_model(model_name)
            try:
                status = await model.get_status()
                for rel in status.relations or []:
                    endpoints = rel.endpoints or []
                    provider = next((e for e in endpoints if e.role == "provider"), None)
                    requirer = next((e for e in endpoints if e.role == "requirer"), None)
                    peer = next((e for e in endpoints if e.role == "peer"), None)
                    if peer:
                        relations.append(
                            RelationInfo(
                                model=model_name,
                                provider=f"{peer.application}:{peer.name}",
                                requirer=f"{peer.application}:{peer.name}",
                                interface=rel.interface or "",
                                type="peer",
                            )
                        )
                    elif provider and requirer:
                        relations.append(
                            RelationInfo(
                                model=model_name,
                                provider=f"{provider.application}:{provider.name}",
                                requirer=f"{requirer.application}:{requirer.name}",
                                interface=rel.interface or "",
                                type="regular",
                            )
                        )
            finally:
                await model.disconnect()
        except Exception:
            logger.exception("Failed to get relations for model '%s'", model_name)
        logger.debug("Fetched %d relations for model '%s'", len(relations), model_name)
        return relations
