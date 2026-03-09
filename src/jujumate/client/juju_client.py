import asyncio
import base64
import json
import logging
import ssl as ssl_module
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import websockets
from juju.client import client as juju_client
from juju.controller import Controller

from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    ControllerOfferInfo,
    LogEntry,
    MachineInfo,
    ModelInfo,
    OfferEndpoint,
    OfferInfo,
    RelationDataEntry,
    RelationInfo,
    SAASInfo,
    SecretInfo,
    UnitInfo,
)

logger = logging.getLogger(__name__)


def _utc_ts_to_local_hms(ts_raw: str) -> str:
    """Convert a Juju RFC3339/nanosecond UTC timestamp to local-time HH:MM:SS.

    Juju timestamps look like ``"2024-03-07T15:30:45.123456789Z"``.
    Python's fromisoformat only accepts up to microseconds, so we truncate
    the fractional part to 6 digits before parsing.
    """
    if "T" not in ts_raw:
        return ts_raw[:8]
    try:
        date_part, time_part = ts_raw.split("T", 1)
        dot = time_part.find(".")
        if dot >= 0:
            # Find where the fractional digits end (Z or +/-)
            end = dot + 1
            while end < len(time_part) and time_part[end].isdigit():
                end += 1
            frac = time_part[dot + 1 : end][:6]  # truncate nanoseconds → microseconds
            time_clean = time_part[: dot + 1] + frac + time_part[end:]
        else:
            time_clean = time_part
        iso = f"{date_part}T{time_clean.replace('Z', '+00:00')}"
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M:%S")
    except Exception:
        return ts_raw.split("T")[1][:8] if "T" in ts_raw else ts_raw[:8]


def _s(v: Any) -> str:
    """Coerce python-libjuju bytes|str|None to str."""
    if v is None:
        return ""
    return v.decode() if isinstance(v, bytes) else str(v)


def _decode_secret_value(v: Any) -> str:
    """Decode a Juju secret value.

    Juju stores secret values base64-encoded. Attempt to decode; if the result
    is valid UTF-8 use it, otherwise return the original string unchanged.
    """
    raw = _s(v)
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        return decoded
    except Exception:
        return raw


class JujuClientError(Exception):
    pass


class JujuClient:
    def __init__(self, controller_name: str | None = None) -> None:
        self._controller_name = controller_name
        self._controller = Controller()

    async def connect(self) -> None:
        logger.debug("Connecting to controller: %s", self._controller_name or "current")
        try:
            if self._controller_name:
                await self._controller.connect(self._controller_name)
            else:
                await self._controller.connect_current()
        except Exception as e:
            raise JujuClientError(f"Failed to connect to controller: {e}") from e
        logger.debug("Connected to controller: %s", self._controller.controller_name)

    async def disconnect(self) -> None:
        logger.debug("Disconnecting from controller: %s", self._controller_name or "current")
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
            logger.exception(
                "Failed to get controller info for '%s'", self._controller_name or "current"
            )
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
    ) -> tuple[ModelInfo, list[AppInfo], list[UnitInfo], list[MachineInfo]]:
        """Fetch ModelInfo, AppInfo list, UnitInfo list, and MachineInfo list.

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
                    if app_st is None:
                        continue
                    charm_name = (
                        model.applications[app_name].charm_name
                        if app_name in model.applications
                        else _s(app_st.charm).split("/")[-1].rsplit("-", 1)[0]
                    )
                    apps.append(
                        AppInfo(
                            name=app_name,
                            model=model_name,
                            charm=_s(charm_name),
                            channel=_s(app_st.charm_channel),
                            revision=app_st.charm_rev or 0,
                            unit_count=len(app_st.units or {}),
                            status=_s(app_st.status.status) if app_st.status else "",
                            message=_s(app_st.status.info) if app_st.status else "",
                            version=_s(app_st.workload_version),
                            address=_s(app_st.public_address),
                            exposed=bool(app_st.exposed),
                            can_upgrade_to=_s(app_st.can_upgrade_to),
                            controller=self._controller_name or "",
                        )
                    )
                    for unit_name, unit_st in (app_st.units or {}).items():
                        if unit_st is None:
                            continue
                        ports_list: list[str] = [_s(p) for p in (unit_st.opened_ports or [])]
                        ports_str = ", ".join(ports_list) if ports_list else ""
                        units.append(
                            UnitInfo(
                                name=unit_name,
                                app=app_name,
                                model=model_name,
                                machine=_s(unit_st.machine),
                                workload_status=_s(unit_st.workload_status.status)
                                if unit_st.workload_status
                                else "",
                                agent_status=_s(unit_st.agent_status.status)
                                if unit_st.agent_status
                                else "",
                                address=_s(unit_st.address),
                                public_address=_s(unit_st.public_address),
                                ports=ports_str,
                                message=_s(unit_st.workload_status.info)
                                if unit_st.workload_status
                                else "",
                                controller=self._controller_name or "",
                            )
                        )
                        for sub_name, sub_st in (unit_st.subordinates or {}).items():
                            if sub_st is None:
                                continue
                            sub_app = sub_name.split("/")[0]
                            units.append(
                                UnitInfo(
                                    name=sub_name,
                                    app=sub_app,
                                    model=model_name,
                                    machine=_s(unit_st.machine),
                                    workload_status=_s(sub_st.workload_status.status)
                                    if sub_st.workload_status
                                    else "",
                                    agent_status=_s(sub_st.agent_status.status)
                                    if sub_st.agent_status
                                    else "",
                                    address=_s(sub_st.address) or _s(unit_st.address),
                                    public_address=_s(sub_st.public_address)
                                    or _s(unit_st.public_address),
                                    ports=", ".join([_s(p) for p in (sub_st.opened_ports or [])]),
                                    message=_s(sub_st.workload_status.info)
                                    if sub_st.workload_status
                                    else "",
                                    subordinate_of=unit_name,
                                    controller=self._controller_name or "",
                                )
                            )
                machines = []
                for m_id, m_st in (full_status.machines or {}).items():
                    if m_st is None:
                        continue
                    base_str = ""
                    if m_st.base:
                        base_str = (
                            f"{_s(m_st.base.name)}@{_s(m_st.base.channel)}"
                            if m_st.base.name
                            else ""
                        )
                    az = ""
                    if m_st.hardware:
                        for part in _s(m_st.hardware).split():
                            if part.startswith("availability-zone="):
                                az = part.split("=", 1)[1]
                                break
                    machines.append(
                        MachineInfo(
                            model=model_name,
                            id=m_id,
                            state=_s(m_st.agent_status.status) if m_st.agent_status else "",
                            address=_s(m_st.dns_name),
                            instance_id=_s(m_st.instance_id),
                            base=base_str,
                            az=az,
                            message=_s(m_st.instance_status.info) if m_st.instance_status else "",
                            controller=self._controller_name or "",
                        )
                    )
            finally:
                await model.disconnect()
        except Exception:
            logger.exception(
                "Failed to get snapshot for model '%s', using minimal info", model_name
            )
            model_info = ModelInfo(
                name=model_name,
                controller=controller_name,
                cloud="",
                region="",
                status="unknown",
            )
            apps = []
            units = []
            machines = []
        logger.debug(
            "Snapshot for model '%s': %d apps, %d units, %d machines",
            model_name,
            len(apps),
            len(units),
            len(machines),
        )
        return model_info, apps, units, machines

    async def get_models(self) -> list[ModelInfo]:
        model_names = await self._controller.list_models()
        controller_name = self._controller.controller_name or ""
        logger.debug("Listing models for controller '%s': %s", controller_name, model_names)
        models = []
        for name in model_names:
            model_info, _, _, _ = await self.get_model_snapshot(name)
            models.append(model_info)
        logger.debug("Fetched %d models for controller '%s'", len(models), controller_name)
        return models

    async def get_applications(self, model_name: str) -> list[AppInfo]:
        _, apps, _, _ = await self.get_model_snapshot(model_name)
        logger.debug("Fetched %d applications for model '%s'", len(apps), model_name)
        return apps

    async def get_units(self, model_name: str) -> list[UnitInfo]:
        _, _, units, _ = await self.get_model_snapshot(model_name)
        logger.debug("Fetched %d units for model '%s'", len(units), model_name)
        return units

    async def get_status_details(
        self, model_name: str
    ) -> tuple[list[RelationInfo], list[OfferInfo], list[SAASInfo]]:
        """Fetch relations, offers and SAAS for a model in a single connection."""
        relations: list[RelationInfo] = []
        offers: list[OfferInfo] = []
        saas: list[SAASInfo] = []
        model = await self._controller.get_model(model_name)
        try:
            status = await model.get_status()
            app_statuses = status.applications or {}
            for rel in status.relations or []:
                if rel is None:
                    continue
                endpoints: list = list(rel.endpoints or [])
                provider = next(
                    (e for e in endpoints if e is not None and e.role == "provider"), None
                )
                requirer = next(
                    (e for e in endpoints if e is not None and e.role == "requirer"), None
                )
                peer = next((e for e in endpoints if e is not None and e.role == "peer"), None)
                if peer:
                    relations.append(
                        RelationInfo(
                            model=model_name,
                            provider=f"{peer.application}:{peer.name}",
                            requirer=f"{peer.application}:{peer.name}",
                            interface=_s(rel.interface),
                            type="peer",
                            relation_id=int(rel.id_ or 0),
                            controller=self._controller_name or "",
                        )
                    )
                elif provider and requirer:
                    relations.append(
                        RelationInfo(
                            model=model_name,
                            provider=f"{provider.application}:{provider.name}",
                            requirer=f"{requirer.application}:{requirer.name}",
                            interface=_s(rel.interface),
                            type="regular",
                            relation_id=int(rel.id_ or 0),
                            controller=self._controller_name or "",
                        )
                    )
            for offer_name, offer_st in (status.offers or {}).items():
                if offer_st is None:
                    continue
                app_name = _s(offer_st.application_name)
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
                    if ep is None:
                        continue
                    offers.append(
                        OfferInfo(
                            model=model_name,
                            name=offer_name,
                            application=app_name,
                            charm=_s(charm_name),
                            rev=rev or 0,
                            connected=connected,
                            endpoint=ep_name,
                            interface=_s(ep.interface),
                            role=_s(ep.role),
                            controller=self._controller_name or "",
                        )
                    )
            # Juju 3.6+ renamed "remote-applications" to "application-endpoints".
            # python-libjuju doesn't know about the new field yet, so it ends up in unknown_fields.
            app_endpoints: dict = (status.unknown_fields or {}).get("application-endpoints", {})
            remote_apps: dict = status.remote_applications or {}
            for remote_name, ep in app_endpoints.items():
                offer_url = ep.get("url", "") if isinstance(ep, dict) else ""
                store = offer_url.split(":")[0] if ":" in offer_url else "local"
                app_status = ep.get("application-status", {}) if isinstance(ep, dict) else {}
                saas.append(
                    SAASInfo(
                        model=model_name,
                        name=remote_name,
                        status=app_status.get("current", "")
                        if isinstance(app_status, dict)
                        else "",
                        store=store,
                        url=offer_url,
                        controller=self._controller_name or "",
                    )
                )
            for remote_name, remote_st in remote_apps.items():
                offer_url = remote_st.offer_url or ""
                store = offer_url.split(":")[0] if ":" in offer_url else "local"
                saas.append(
                    SAASInfo(
                        model=model_name,
                        name=remote_name,
                        status=remote_st.status.status if remote_st.status else "",
                        store=store,
                        url=offer_url,
                        controller=self._controller_name or "",
                    )
                )
        finally:
            await model.disconnect()
        logger.debug(
            "Status details for model '%s': %d relations, %d offers, %d saas",
            model_name,
            len(relations),
            len(offers),
            len(saas),
        )
        return relations, offers, saas

    async def get_secrets(self, model_name: str) -> list[SecretInfo]:
        """Fetch all secrets visible in the given model."""
        secrets: list[SecretInfo] = []
        model = await self._controller.get_model(model_name)
        try:
            results = await model.list_secrets()
            for s in results or []:
                owner = getattr(s, "owner_tag", "") or ""
                # Strip "application-" / "model-" prefix from owner tag
                if "-" in owner:
                    owner = owner.split("-", 1)[1]
                secrets.append(
                    SecretInfo(
                        uri=getattr(s, "uri", "") or "",
                        label=getattr(s, "label", "") or "",
                        owner=owner,
                        description=getattr(s, "description", "") or "",
                        revision=getattr(s, "latest_revision", 0) or 0,
                        rotate_policy=getattr(s, "rotate_policy", "") or "",
                        created=getattr(s, "create_time", "") or "",
                        updated=getattr(s, "update_time", "") or "",
                    )
                )
        finally:
            await model.disconnect()
        logger.debug("Secrets for '%s': %d entries", model_name, len(secrets))
        return secrets

    async def get_secret_content(self, model_name: str, secret_uri: str) -> dict[str, str]:
        """Fetch the key-value content of a secret by URI (requires show_secrets=True)."""
        model = await self._controller.get_model(model_name)
        try:
            results = await model.list_secrets(show_secrets=True)
            for s in results or []:
                if getattr(s, "uri", "") == secret_uri:
                    value = getattr(s, "value", None)
                    if value is not None:
                        data = getattr(value, "data", None)
                        if data:
                            return {k: _decode_secret_value(v) for k, v in data.items()}
            return {}
        finally:
            await model.disconnect()

    async def get_app_config(self, model_name: str, app_name: str) -> list[AppConfigEntry]:
        """Fetch configuration entries for an application."""
        entries: list[AppConfigEntry] = []
        model = await self._controller.get_model(model_name)
        try:
            app = model.applications.get(app_name)
            if not app:
                logger.warning(
                    "get_app_config: app '%s' not found in model '%s'", app_name, model_name
                )
                return entries
            config = await app.get_config()
            for key, data in sorted(config.items()):
                if not isinstance(data, dict):
                    continue
                source = str(data.get("source", "default"))
                value = str(data.get("value", ""))
                default = str(data.get("default", value if source == "default" else ""))
                entries.append(
                    AppConfigEntry(
                        key=key,
                        value=value,
                        default=default,
                        type=str(data.get("type", "")),
                        description=str(data.get("description", "")),
                        source=source,
                    )
                )
        finally:
            await model.disconnect()
        logger.debug("App config for '%s/%s': %d entries", model_name, app_name, len(entries))
        return entries

    async def get_relations(self, model_name: str) -> list[RelationInfo]:
        relations, _, _ = await self.get_status_details(model_name)
        return relations

    async def get_saas(self, model_name: str) -> list[SAASInfo]:
        """Fetch SAAS (consumed remote offers) entries for a model."""
        _, _, saas = await self.get_status_details(model_name)
        return saas

    async def get_relation_data(
        self,
        model_name: str,
        relation_id: int,
        provider_app: str,
        requirer_app: str,
    ) -> list[RelationDataEntry]:
        """Fetch relation data bags for both sides of a relation.

        Calls Application.UnitsInfo for one unit on each side.  From the
        provider unit we get: provider app-level data + requirer units' data.
        From the requirer unit we get: requirer app-level data + provider units' data.
        """
        model = await self._controller.get_model(model_name)
        try:
            facade = juju_client.ApplicationFacade.from_connection(model.connection())
            entries: list[RelationDataEntry] = []
            is_peer = provider_app == requirer_app
            sides: list[tuple[str, str, str, str]] = []  # (app, own_side, other_side, other_app)
            if is_peer:
                sides = [(provider_app, "peer", "peer", provider_app)]
            else:
                sides = [
                    (provider_app, "provider", "requirer", requirer_app),
                    (requirer_app, "requirer", "provider", provider_app),
                ]

            for app_name, _own_side, other_side, other_app_name in sides:
                app = model.applications.get(app_name)
                if not app or not app.units:
                    continue
                unit_obj = next(iter(app.units))
                unit_tag = "unit-" + unit_obj.name.replace("/", "-")
                result = await facade.UnitsInfo(entities=[juju_client.Entity(unit_tag)])
                if not result.results:
                    continue
                unit_result = result.results[0]
                if unit_result.error or not unit_result.result:
                    continue
                for ep_data in unit_result.result.relation_data or []:
                    if ep_data.relation_id != relation_id:
                        continue
                    # Application-level data bag (remote side's app data)
                    if ep_data.applicationdata:
                        for k, v in sorted(ep_data.applicationdata.items()):
                            entries.append(
                                RelationDataEntry(
                                    side=other_side,
                                    unit=other_app_name,
                                    key=k,
                                    value=str(v),
                                    scope="app",
                                )
                            )
                    # Unit-level data bags from the OTHER side's units
                    for unit_n, rel_data in (ep_data.unit_relation_data or {}).items():
                        if rel_data and rel_data.unitdata:
                            for k, v in sorted(rel_data.unitdata.items()):
                                entries.append(
                                    RelationDataEntry(
                                        side=other_side,
                                        unit=unit_n,
                                        key=k,
                                        value=str(v),
                                        scope="unit",
                                    )
                                )
        finally:
            await model.disconnect()
        logger.debug("Relation data for relation %d: %d entries", relation_id, len(entries))
        return entries

    async def get_offer_detail(
        self, model_name: str, offer_name: str
    ) -> ControllerOfferInfo | None:
        """Fetch detail for a single named offer in a model."""
        try:
            raw = await self._controller.list_offers(model_name)
            model = await self._controller.get_model(model_name)
            status_counts: dict[str, tuple[int, int]] = {}
            try:
                status = await model.get_status()
                for name, offer_st in (status.offers or {}).items():
                    if offer_st is None:
                        continue
                    status_counts[name] = (
                        offer_st.active_connected_count or 0,
                        offer_st.total_connected_count or 0,
                    )
            finally:
                await model.disconnect()
            _access_rank = {"admin": 3, "consume": 2, "read": 1}
            for offer in raw.results or []:
                if (offer.offer_name or "") != offer_name:
                    continue
                endpoints = [
                    OfferEndpoint(
                        name=ep.name or "",
                        interface=ep.interface or "",
                        role=ep.role or "",
                    )
                    for ep in (offer.endpoints or [])
                ]
                active, total = status_counts.get(offer_name, (0, 0))
                users = offer.users or []
                access = max(
                    (getattr(u, "access", "") or "" for u in users),
                    key=lambda a: _access_rank.get(a, 0),
                    default="",
                )
                return ControllerOfferInfo(
                    model=model_name,
                    name=offer_name,
                    offer_url=offer.offer_url or "",
                    application=offer.application_name or "",
                    charm=offer.charm_url or "",
                    description=offer.application_description or "",
                    access=access,
                    endpoints=endpoints,
                    active_connections=active,
                    total_connections=total,
                )
        except Exception:
            logger.warning(
                "Could not fetch offer detail for '%s' in model '%s'", offer_name, model_name
            )
        return None

    async def get_controller_offers(self) -> list[ControllerOfferInfo]:
        """Fetch all offers across every model in the controller."""
        model_names = await self._controller.list_models()
        result: list[ControllerOfferInfo] = []
        for model_name in model_names:
            try:
                raw = await self._controller.list_offers(model_name)
                # Get reliable connection counts from model status (same source as `juju status`).
                status_counts: dict[str, tuple[int, int]] = {}
                model = await self._controller.get_model(model_name)
                try:
                    status = await model.get_status()
                    for offer_name, offer_st in (status.offers or {}).items():
                        if offer_st is None:
                            continue
                        status_counts[offer_name] = (
                            offer_st.active_connected_count or 0,
                            offer_st.total_connected_count or 0,
                        )
                finally:
                    await model.disconnect()
                for offer in raw.results or []:
                    endpoints = [
                        OfferEndpoint(
                            name=ep.name or "",
                            interface=ep.interface or "",
                            role=ep.role or "",
                        )
                        for ep in (offer.endpoints or [])
                    ]
                    active, total = status_counts.get(offer.offer_name or "", (0, 0))
                    # Determine access level: pick the highest from the users list.
                    _access_rank = {"admin": 3, "consume": 2, "read": 1}
                    users = offer.users or []
                    access = max(
                        (getattr(u, "access", "") or "" for u in users),
                        key=lambda a: _access_rank.get(a, 0),
                        default="",
                    )
                    result.append(
                        ControllerOfferInfo(
                            model=model_name,
                            name=offer.offer_name or "",
                            offer_url=offer.offer_url or "",
                            application=offer.application_name or "",
                            charm=offer.charm_url or "",
                            description=offer.application_description or "",
                            access=access,
                            endpoints=endpoints,
                            active_connections=active,
                            total_connections=total,
                        )
                    )
            except Exception:
                logger.warning("Could not list offers for model '%s'", model_name)
        logger.debug("Controller offers: %d total", len(result))
        return result

    async def stream_logs(
        self,
        model_name: str,
        level: str = "DEBUG",
    ) -> AsyncGenerator[LogEntry, None]:
        """Stream live log entries from a Juju model.

        Connects directly to the Juju debug-log WebSocket endpoint.
        Uses ``backlog=100`` to show the last 100 lines as recent context and
        then streams new log entries as they arrive.

        Yields LogEntry objects as they arrive from the controller.
        The generator runs until cancelled (e.g. when the log screen is closed).

        Args:
            model_name: Model to stream logs from.
            level: Minimum log level — TRACE, DEBUG, INFO, WARNING, ERROR.
        """
        uuids = await self._controller.model_uuids()
        uuid = uuids.get(model_name)
        if not uuid:
            raise JujuClientError(f"Model '{model_name}' not found")

        conn = self._controller.connection()
        params = conn.connect_params()
        endpoint = params["endpoint"]
        if isinstance(endpoint, list):
            endpoint = endpoint[0]
        username = conn.username
        password = params["password"]
        cacert = params["cacert"]

        if not password:
            raise JujuClientError("Live log streaming requires username/password authentication")

        url = (
            f"wss://user-{username}:{password}@{endpoint}"
            f"/model/{uuid}/log?backlog=100&level={level}"
        )

        if cacert:
            ssl_ctx: ssl_module.SSLContext | bool = ssl_module.create_default_context(
                purpose=ssl_module.Purpose.SERVER_AUTH, cadata=cacert
            )
            # Controller certs don't contain the IP/hostname — safe to skip check
            ssl_ctx.check_hostname = False  # type: ignore[union-attr]
        else:
            ssl_ctx = True

        while True:
            try:
                async with websockets.connect(url, ssl=ssl_ctx, ping_interval=None) as ws:
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            ts_raw: str = data.get("ts", "")
                            yield LogEntry(
                                timestamp=_utc_ts_to_local_hms(ts_raw),
                                level=data.get("sev", ""),
                                entity=data.get("tag", ""),
                                module=data.get("mod", ""),
                                message=data.get("msg", ""),
                            )
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
            except asyncio.CancelledError:
                return
            except websockets.ConnectionClosed:
                logger.debug("Log stream connection closed, reconnecting…")
                await asyncio.sleep(2)
                continue
            except Exception:
                return
