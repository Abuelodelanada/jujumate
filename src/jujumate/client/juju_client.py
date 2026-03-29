import asyncio
import base64
import binascii
import json
import logging
import re
import ssl as ssl_module
from collections.abc import AsyncGenerator, Callable
from datetime import datetime
from typing import Any

import websockets
import websockets.exceptions
from juju.client import client as juju_client
from juju.controller import Controller
from juju.errors import JujuError

from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    ControllerOfferInfo,
    LogEntry,
    MachineInfo,
    ModelInfo,
    NetworkInterface,
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
    try:
        normalized = re.sub(r"(\.\d{6})\d*", r"\1", ts_raw).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone().strftime("%H:%M:%S")
    except ValueError:
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
    except (binascii.Error, UnicodeDecodeError):
        return raw


class JujuClientError(Exception):
    pass


def _parse_model_info(
    model: Any, full_status: Any, model_name: str, controller_name: str
) -> ModelInfo:
    info = model.info
    cloud_tag = (info.cloud_tag or "") if info else ""
    cloud = cloud_tag.split("-", 1)[-1] if "-" in cloud_tag else cloud_tag
    app_statuses = full_status.applications or {}
    is_kubernetes = getattr(info, "type_", "") == "caas" if info else False
    return ModelInfo(
        name=model_name,
        controller=controller_name,
        cloud=cloud,
        region=(info.cloud_region or "") if info else "",
        status=info.status.status if info and info.status else "",
        machine_count=len(full_status.machines or {}),
        app_count=len(app_statuses),
        is_kubernetes=is_kubernetes,
    )


def _parse_app_info(
    app_name: str, app_st: Any, model: Any, model_name: str, controller_name: str
) -> AppInfo:
    charm_name = (
        model.applications[app_name].charm_name
        if app_name in model.applications
        else _s(app_st.charm).split("/")[-1].rsplit("-", 1)[0]
    )
    return AppInfo(
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
        controller=controller_name,
    )


def _parse_unit_info(
    unit_name: str, unit_st: Any, app_name: str, model_name: str, controller_name: str
) -> UnitInfo:
    ports_list: list[str] = [_s(p) for p in (unit_st.opened_ports or [])]
    ports_str = ", ".join(ports_list) if ports_list else ""
    return UnitInfo(
        name=unit_name,
        app=app_name,
        model=model_name,
        machine=_s(unit_st.machine),
        workload_status=_s(unit_st.workload_status.status) if unit_st.workload_status else "",
        agent_status=_s(unit_st.agent_status.status) if unit_st.agent_status else "",
        address=_s(unit_st.address),
        public_address=_s(unit_st.public_address),
        ports=ports_str,
        message=_s(unit_st.workload_status.info) if unit_st.workload_status else "",
        is_leader=bool(unit_st.leader),
        controller=controller_name,
    )


def _parse_subordinate(
    sub_name: str,
    sub_st: Any,
    unit_st: Any,
    unit_name: str,
    model_name: str,
    controller_name: str,
) -> UnitInfo:
    sub_app = sub_name.split("/")[0]
    return UnitInfo(
        name=sub_name,
        app=sub_app,
        model=model_name,
        machine=_s(unit_st.machine),
        workload_status=_s(sub_st.workload_status.status) if sub_st.workload_status else "",
        agent_status=_s(sub_st.agent_status.status) if sub_st.agent_status else "",
        address=_s(sub_st.address) or _s(unit_st.address),
        public_address=_s(sub_st.public_address) or _s(unit_st.public_address),
        ports=", ".join([_s(p) for p in (sub_st.opened_ports or [])]),
        message=_s(sub_st.workload_status.info) if sub_st.workload_status else "",
        subordinate_of=unit_name,
        controller=controller_name,
    )


_HW_PARSERS: dict[str, Callable[[str], Any]] = {
    "arch": lambda v: v,
    "cores": lambda v: int(v),
    "mem": lambda v: int(v.rstrip("M")),
    "root-disk": lambda v: int(v.rstrip("M")),
    "virt-type": lambda v: v,
    "availability-zone": lambda v: v,
}


def _parse_hw(hardware: str) -> dict[str, Any]:
    """Parse a Juju hardware string into a dict keyed by field name."""
    result: dict[str, Any] = {}
    for part in hardware.split():
        key, _, val = part.partition("=")
        if key in _HW_PARSERS:
            try:
                result[key] = _HW_PARSERS[key](val)
            except ValueError:
                pass
    return result


def _since_to_iso(since: Any) -> str:
    """Return an ISO-8601 string from a datetime-like *since* value, or '' if absent."""
    if not since:
        return ""
    try:
        return since.isoformat()
    except AttributeError:
        return _s(since)


def _parse_machine_info(m_id: str, m_st: Any, model_name: str, controller_name: str) -> MachineInfo:
    base_str = ""
    if m_st.base:
        base_str = f"{_s(m_st.base.name)}@{_s(m_st.base.channel)}" if m_st.base.name else ""

    hw = _parse_hw(_s(m_st.hardware)) if m_st.hardware else {}

    nics: list[NetworkInterface] = []
    if m_st.network_interfaces:
        for iface_name, iface in m_st.network_interfaces.items():
            ip_list = getattr(iface, "ip_addresses", None) or []
            ips = [_s(a) for a in ip_list if a]
            nics.append(
                NetworkInterface(
                    name=iface_name,
                    ips=ips,
                    mac=_s(getattr(iface, "mac_address", "")),
                    space=_s(getattr(iface, "space", "")),
                )
            )

    return MachineInfo(
        model=model_name,
        id=m_id,
        state=_s(m_st.agent_status.status) if m_st.agent_status else "",
        address=_s(m_st.dns_name),
        instance_id=_s(m_st.instance_id),
        base=base_str,
        az=hw.get("availability-zone", ""),
        message=_s(m_st.instance_status.info) if m_st.instance_status else "",
        controller=controller_name,
        hardware_arch=hw.get("arch", ""),
        hardware_cores=hw.get("cores", 0),
        hardware_mem_mib=hw.get("mem", 0),
        hardware_disk_mib=hw.get("root-disk", 0),
        hardware_virt_type=hw.get("virt-type", ""),
        agent_since=_since_to_iso(m_st.agent_status.since if m_st.agent_status else None),
        instance_status=_s(m_st.instance_status.status) if m_st.instance_status else "",
        instance_since=_since_to_iso(m_st.instance_status.since if m_st.instance_status else None),
        network_interfaces=nics,
    )


def _parse_relation(rel: Any, model_name: str, controller_name: str) -> RelationInfo | None:
    endpoints = list(rel.endpoints or [])
    provider = next((e for e in endpoints if e is not None and e.role == "provider"), None)
    requirer = next((e for e in endpoints if e is not None and e.role == "requirer"), None)
    peer = next((e for e in endpoints if e is not None and e.role == "peer"), None)
    if peer:
        return RelationInfo(
            model=model_name,
            provider=f"{peer.application}:{peer.name}",
            requirer=f"{peer.application}:{peer.name}",
            interface=_s(rel.interface),
            type="peer",
            relation_id=int(rel.id_ or 0),
            controller=controller_name,
        )
    elif provider and requirer:
        return RelationInfo(
            model=model_name,
            provider=f"{provider.application}:{provider.name}",
            requirer=f"{requirer.application}:{requirer.name}",
            interface=_s(rel.interface),
            type="regular",
            relation_id=int(rel.id_ or 0),
            controller=controller_name,
        )
    return None


def _parse_offer_endpoints(
    offer_name: str,
    offer_st: Any,
    model: Any,
    app_statuses: dict,
    model_name: str,
    controller_name: str,
) -> list[OfferInfo]:
    app_name = _s(offer_st.application_name)
    app_st = app_statuses.get(app_name)
    rev = app_st.charm_rev if app_st else 0
    charm_name = (
        model.applications[app_name].charm_name if app_name in model.applications else app_name
    )
    active = offer_st.active_connected_count or 0
    total = offer_st.total_connected_count or 0
    connected = f"{active}/{total}"
    return [
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
            controller=controller_name,
        )
        for ep_name, ep in (offer_st.endpoints or {}).items()
        if ep is not None
    ]


def _parse_saas_app_endpoint(name: str, ep: Any, model_name: str, controller_name: str) -> SAASInfo:
    offer_url = ep.get("url", "") if isinstance(ep, dict) else ""
    store = offer_url.split(":")[0] if ":" in offer_url else "local"
    app_status = ep.get("application-status", {}) if isinstance(ep, dict) else {}
    return SAASInfo(
        model=model_name,
        name=name,
        status=app_status.get("current", "") if isinstance(app_status, dict) else "",
        store=store,
        url=offer_url,
        controller=controller_name,
    )


def _parse_saas_remote_app(
    name: str, remote_st: Any, model_name: str, controller_name: str
) -> SAASInfo:
    offer_url = remote_st.offer_url or ""
    store = offer_url.split(":")[0] if ":" in offer_url else "local"
    return SAASInfo(
        model=model_name,
        name=name,
        status=remote_st.status.status if remote_st.status else "",
        store=store,
        url=offer_url,
        controller=controller_name,
    )


def _relation_sides(provider_app: str, requirer_app: str) -> list[tuple[str, str, str, str]]:
    """Return the list of (app_name, own_side, other_side, other_app_name) tuples for a relation."""
    if provider_app == requirer_app:
        return [(provider_app, "peer", "peer", provider_app)]
    return [
        (provider_app, "provider", "requirer", requirer_app),
        (requirer_app, "requirer", "provider", provider_app),
    ]


def _parse_app_relation_data(
    ep_data: Any, other_side: str, other_app_name: str
) -> list[RelationDataEntry]:
    """Return application-level RelationDataEntry items from an endpoint data bag."""
    if not ep_data.applicationdata:
        return []
    return [
        RelationDataEntry(side=other_side, unit=other_app_name, key=k, value=str(v), scope="app")
        for k, v in sorted(ep_data.applicationdata.items())
    ]


def _parse_unit_relation_data(ep_data: Any, other_side: str) -> list[RelationDataEntry]:
    """Return unit-level RelationDataEntry items from an endpoint data bag."""
    entries: list[RelationDataEntry] = []
    for unit_n, rel_data in (ep_data.unit_relation_data or {}).items():
        if not rel_data:
            continue
        if not rel_data.unitdata:
            continue
        for k, v in sorted(rel_data.unitdata.items()):
            entries.append(
                RelationDataEntry(side=other_side, unit=unit_n, key=k, value=str(v), scope="unit")
            )
    return entries


def _offer_status_counts(status: Any) -> dict[str, tuple[int, int]]:
    """Extract {offer_name: (active_connected, total_connected)} from a model status object."""
    counts: dict[str, tuple[int, int]] = {}
    for name, offer_st in (status.offers or {}).items():
        if offer_st is None:
            continue
        counts[name] = (
            offer_st.active_connected_count or 0,
            offer_st.total_connected_count or 0,
        )
    return counts


def _build_offer_endpoints(offer: Any) -> list[OfferEndpoint]:
    """Build a list of OfferEndpoint from a raw offer's endpoints."""
    return [
        OfferEndpoint(
            name=ep.name or "",
            interface=ep.interface or "",
            role=ep.role or "",
        )
        for ep in (offer.endpoints or [])
    ]


def _build_controller_offer_info(
    offer: Any, model_name: str, status_counts: dict[str, tuple[int, int]]
) -> ControllerOfferInfo:
    """Combine a raw offer and status_counts into a ControllerOfferInfo."""
    _access_rank = {"admin": 3, "consume": 2, "read": 1}
    offer_name = offer.offer_name or ""
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
        endpoints=_build_offer_endpoints(offer),
        active_connections=active,
        total_connections=total,
    )


async def _resolve_model_uuid(controller: Controller, model_name: str) -> str:
    """Look up the UUID for *model_name* on *controller*.

    Raises JujuClientError if the model is not found.
    """
    uuids = await controller.model_uuids()
    uuid = uuids.get(model_name)
    if not uuid:
        raise JujuClientError(f"Model '{model_name}' not found")
    return uuid


def _log_stream_connection_params(controller: Controller) -> tuple[str, str, str, str | None]:
    """Extract ``(endpoint, username, password, cacert)`` from *controller*'s connection.

    Raises JujuClientError if *password* is empty (token-based auth is not supported
    for the raw WebSocket log endpoint).
    """
    conn = controller.connection()
    params = conn.connect_params()
    endpoint: str = params["endpoint"]
    if isinstance(endpoint, list):
        endpoint = endpoint[0]
    username: str = conn.username or ""
    password: str = params["password"]
    cacert: str | None = params["cacert"]
    if not password:
        raise JujuClientError("Live log streaming requires username/password authentication")
    return endpoint, username, password, cacert


def _build_log_stream_url(
    endpoint: str, username: str, password: str, uuid: str, level: str
) -> str:
    """Return the ``wss://`` URL for the Juju model debug-log WebSocket endpoint."""
    return f"wss://user-{username}:{password}@{endpoint}/model/{uuid}/log?backlog=100&level={level}"


def _build_ssl_context(cacert: str | None) -> ssl_module.SSLContext | bool:
    """Return an SSLContext loaded with *cacert*, or ``True`` to use default verification."""
    if cacert:
        ctx = ssl_module.create_default_context(
            purpose=ssl_module.Purpose.SERVER_AUTH, cadata=cacert
        )
        # Controller certs don't contain the IP/hostname — safe to skip check
        ctx.check_hostname = False
        return ctx
    return True


def _parse_log_entry(message: str | bytes) -> LogEntry:
    """Parse a JSON WebSocket message string into a LogEntry.

    May raise ``json.JSONDecodeError``, ``KeyError``, or ``IndexError``.
    """
    data = json.loads(message)
    ts_raw: str = data.get("ts", "")
    return LogEntry(
        timestamp=_utc_ts_to_local_hms(ts_raw),
        level=data.get("sev", ""),
        entity=data.get("tag", ""),
        module=data.get("mod", ""),
        message=data.get("msg", ""),
    )


class JujuClient:
    def __init__(
        self,
        controller_name: str | None = None,
        controller: Controller | None = None,
    ) -> None:
        self._controller_name = controller_name
        self._controller = controller if controller is not None else Controller()

    async def connect(self) -> None:
        logger.debug("Connecting to controller: %s", self._controller_name or "current")
        try:
            if self._controller_name:
                await self._controller.connect(self._controller_name)
            else:
                await self._controller.connect_current()
        except (JujuError, OSError, asyncio.TimeoutError) as e:
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
        except (JujuError, AttributeError):
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
                full_status = await model.get_status()
                app_statuses = full_status.applications or {}
                model_info = _parse_model_info(model, full_status, model_name, controller_name)
                apps = []
                units = []
                for app_name, app_st in app_statuses.items():
                    if app_st is None:
                        continue
                    apps.append(
                        _parse_app_info(app_name, app_st, model, model_name, controller_name)
                    )
                    for unit_name, unit_st in (app_st.units or {}).items():
                        if unit_st is None:
                            continue
                        units.append(
                            _parse_unit_info(
                                unit_name, unit_st, app_name, model_name, controller_name
                            )
                        )
                        for sub_name, sub_st in (unit_st.subordinates or {}).items():
                            if sub_st is None:
                                continue
                            units.append(
                                _parse_subordinate(
                                    sub_name,
                                    sub_st,
                                    unit_st,
                                    unit_name,
                                    model_name,
                                    controller_name,
                                )
                            )
                machines = [
                    _parse_machine_info(m_id, m_st, model_name, controller_name)
                    for m_id, m_st in (full_status.machines or {}).items()
                    if m_st is not None
                ]
            finally:
                await model.disconnect()
        except JujuError:
            logger.exception(
                "Failed to get snapshot for model '%s', using minimal info", model_name
            )
            model_info = ModelInfo(
                name=model_name, controller=controller_name, cloud="", region="", status="unknown"
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
        try:
            model = await self._controller.get_model(model_name)
        except websockets.exceptions.InvalidStatusCode as exc:
            raise JujuError(f"Model '{model_name}' is no longer available: {exc}") from exc
        try:
            status = await model.get_status()
            app_statuses = status.applications or {}
            controller_name = self._controller_name or ""

            relations = [
                r
                for rel in (status.relations or [])
                if rel is not None
                and (r := _parse_relation(rel, model_name, controller_name)) is not None
            ]
            offers = [
                offer
                for offer_name, offer_st in (status.offers or {}).items()
                if offer_st is not None
                for offer in _parse_offer_endpoints(
                    offer_name, offer_st, model, app_statuses, model_name, controller_name
                )
            ]
            # Juju 3.6+ renamed "remote-applications" to "application-endpoints".
            # python-libjuju doesn't know about the new field yet, so it ends up in unknown_fields.
            app_endpoints: dict = (status.unknown_fields or {}).get("application-endpoints", {})
            remote_apps: dict = status.remote_applications or {}
            saas = [
                _parse_saas_app_endpoint(name, ep, model_name, controller_name)
                for name, ep in app_endpoints.items()
            ] + [
                _parse_saas_remote_app(name, remote_st, model_name, controller_name)
                for name, remote_st in remote_apps.items()
            ]
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
        try:
            model = await self._controller.get_model(model_name)
        except websockets.exceptions.InvalidStatusCode as exc:
            raise JujuError(f"Model '{model_name}' is no longer available: {exc}") from exc
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
        try:
            model = await self._controller.get_model(model_name)
        except websockets.exceptions.InvalidStatusCode as exc:
            raise JujuError(f"Model '{model_name}' is no longer available: {exc}") from exc
        try:
            results = await model.list_secrets(show_secrets=True)
            for s in results or []:
                if getattr(s, "uri", "") != secret_uri:
                    continue

                value = getattr(s, "value", None)
                if value is None:
                    continue

                data = getattr(value, "data", None)
                if not data:
                    continue

                return {k: _decode_secret_value(v) for k, v in data.items()}
            return {}
        finally:
            await model.disconnect()

    async def get_app_config(self, model_name: str, app_name: str) -> list[AppConfigEntry]:
        """Fetch configuration entries for an application."""
        entries: list[AppConfigEntry] = []
        try:
            model = await self._controller.get_model(model_name)
        except websockets.exceptions.InvalidStatusCode as exc:
            raise JujuError(f"Model '{model_name}' is no longer available: {exc}") from exc
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
        try:
            model = await self._controller.get_model(model_name)
        except websockets.exceptions.InvalidStatusCode as exc:
            raise JujuError(f"Model '{model_name}' is no longer available: {exc}") from exc
        try:
            facade = juju_client.ApplicationFacade.from_connection(model.connection())
            entries: list[RelationDataEntry] = []
            for app_name, _own_side, other_side, other_app_name in _relation_sides(
                provider_app, requirer_app
            ):
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
                    entries.extend(_parse_app_relation_data(ep_data, other_side, other_app_name))
                    entries.extend(_parse_unit_relation_data(ep_data, other_side))
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
            try:
                status = await model.get_status()
                status_counts = _offer_status_counts(status)
            finally:
                await model.disconnect()
            for offer in raw.results or []:
                if (offer.offer_name or "") != offer_name:
                    continue
                return _build_controller_offer_info(offer, model_name, status_counts)
        except (JujuError, websockets.exceptions.InvalidStatusCode):
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
                model = await self._controller.get_model(model_name)
                try:
                    status = await model.get_status()
                    status_counts = _offer_status_counts(status)
                finally:
                    await model.disconnect()
                for offer in raw.results or []:
                    result.append(_build_controller_offer_info(offer, model_name, status_counts))
            except (JujuError, websockets.exceptions.InvalidStatusCode):
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
        uuid = await _resolve_model_uuid(self._controller, model_name)
        endpoint, username, password, cacert = _log_stream_connection_params(self._controller)
        url = _build_log_stream_url(endpoint, username, password, uuid, level)
        ssl_ctx = _build_ssl_context(cacert)

        while True:
            try:
                async with websockets.connect(url, ssl=ssl_ctx, ping_interval=None) as ws:
                    async for message in ws:
                        try:
                            yield _parse_log_entry(message)
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
