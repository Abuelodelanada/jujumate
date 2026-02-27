import logging

from juju.controller import Controller

from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, OfferInfo, RelationInfo, UnitInfo

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
        """Fetch ModelInfo, AppInfo list, and UnitInfo list in a single model connection.

        Uses model.get_status() (FullStatus) to get accurate channel, revision,
        address, exposed, and version data that is not available from AllWatcher deltas.
        """
        controller_name = self._controller.controller_name or ""
        try:
            model = await self._controller.get_model(model_name)
            try:
                info = model.info
                cloud_tag = (info.cloud_tag or "") if info else ""
                cloud = cloud_tag.split("-", 1)[-1] if "-" in cloud_tag else cloud_tag
                full_status = await model.get_status()
                app_statuses = full_status.applications or {}
                is_kubernetes = getattr(info, "type_", "") == "caas" if info else False
                model_info = ModelInfo(
                    name=model_name,
                    controller=controller_name,
                    cloud=cloud,
                    region=(info.cloud_region or "") if info else "",
                    status=info.status.status if info and info.status else "",
                    machine_count=len(full_status.machines or {}),
                    app_count=len(app_statuses),
                    is_kubernetes=is_kubernetes,
                )
                apps = []
                units = []
                for app_name, app_st in app_statuses.items():
                    charm_name = model.applications[app_name].charm_name if app_name in model.applications else (app_st.charm or "").split("/")[-1].rsplit("-", 1)[0]
                    apps.append(
                        AppInfo(
                            name=app_name,
                            model=model_name,
                            charm=charm_name,
                            channel=app_st.charm_channel or "",
                            revision=app_st.charm_rev or 0,
                            unit_count=len(app_st.units or {}),
                            status=app_st.status.status if app_st.status else "",
                            message=app_st.status.info if app_st.status else "",
                            version=app_st.workload_version or "",
                            address=app_st.public_address or "",
                            exposed=bool(app_st.exposed),
                        )
                    )
                    for unit_name, unit_st in (app_st.units or {}).items():
                        opened_ports = unit_st.opened_ports or []
                        ports_str = ", ".join(opened_ports) if opened_ports else ""
                        units.append(
                            UnitInfo(
                                name=unit_name,
                                app=app_name,
                                machine=unit_st.machine or "",
                                workload_status=unit_st.workload_status.status if unit_st.workload_status else "",
                                agent_status=unit_st.agent_status.status if unit_st.agent_status else "",
                                address=unit_st.address or "",
                                public_address=unit_st.public_address or "",
                                ports=ports_str,
                                message=unit_st.workload_status.info if unit_st.workload_status else "",
                            )
                        )
                        for sub_name, sub_st in (unit_st.subordinates or {}).items():
                            sub_app = sub_name.split("/")[0]
                            units.append(
                                UnitInfo(
                                    name=sub_name,
                                    app=sub_app,
                                    machine=unit_st.machine or "",
                                    workload_status=sub_st.workload_status.status if sub_st.workload_status else "",
                                    agent_status=sub_st.agent_status.status if sub_st.agent_status else "",
                                    address=sub_st.address or unit_st.address or "",
                                    public_address=sub_st.public_address or unit_st.public_address or "",
                                    ports=", ".join(sub_st.opened_ports or []),
                                    message=sub_st.workload_status.info if sub_st.workload_status else "",
                                    subordinate_of=unit_name,
                                )
                            )
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

    async def get_status_details(
        self, model_name: str
    ) -> tuple[list[RelationInfo], list[OfferInfo]]:
        """Fetch relations and offers for a model in a single connection."""
        relations: list[RelationInfo] = []
        offers: list[OfferInfo] = []
        model = await self._controller.get_model(model_name)
        try:
            status = await model.get_status()
            app_statuses = status.applications or {}
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
            for offer_name, offer_st in (status.offers or {}).items():
                app_name = offer_st.application_name or ""
                app_st = app_statuses.get(app_name)
                rev = app_st.charm_rev if app_st else 0
                charm_name = (
                    model.applications[app_name].charm_name
                    if app_name in model.applications
                    else app_name
                )
                active = offer_st.active_connected_count or 0
                total = offer_st.total_connected_count or 0
                connected = f"{active}/{total}"
                for ep_name, ep in (offer_st.endpoints or {}).items():
                    offers.append(
                        OfferInfo(
                            model=model_name,
                            name=offer_name,
                            application=app_name,
                            charm=charm_name,
                            rev=rev or 0,
                            connected=connected,
                            endpoint=ep_name,
                            interface=ep.interface or "",
                            role=ep.role or "",
                        )
                    )
        finally:
            await model.disconnect()
        logger.debug(
            "Status details for model '%s': %d relations, %d offers",
            model_name, len(relations), len(offers),
        )
        return relations, offers

    async def get_relations(self, model_name: str) -> list[RelationInfo]:
        relations, _ = await self.get_status_details(model_name)
        return relations
