import asyncio
import logging
import time
from pathlib import Path
from typing import TypeVar

from juju.errors import JujuError
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import TabbedContent, TabPane

from jujumate.client.juju_client import JujuClient
from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    ControllersUpdated,
    DataRefreshed,
    JujuPoller,
    MachinesUpdated,
    ModelsUpdated,
    OffersUpdated,
    RelationsUpdated,
    SaasUpdated,
    StorageUpdated,
    UnitsUpdated,
)
from jujumate.config import JujuConfigError, load_config
from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    ControllerOfferInfo,
    MachineInfo,
    ModelInfo,
    OfferInfo,
    RelationInfo,
    SAASInfo,
    StorageInfo,
    UnitInfo,
)
from jujumate.screens.app_config_screen import AppConfigScreen
from jujumate.screens.help_screen import HelpScreen
from jujumate.screens.log_screen import LogScreen
from jujumate.screens.machine_detail_screen import MachineDetailScreen
from jujumate.screens.offers_screen import OfferDetailScreen, OffersScreen
from jujumate.screens.relation_data_screen import RelationDataScreen
from jujumate.screens.secrets_screen import SecretsScreen
from jujumate.screens.settings_screen import SettingsScreen
from jujumate.screens.storage_detail_screen import StorageDetailScreen
from jujumate.settings import AppSettings, load_settings, save_settings
from jujumate.widgets.health_view import HealthView
from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader
from jujumate.widgets.navigator_view import NavigatorView
from jujumate.widgets.status_view import StatusView

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class MainScreen(Screen):
    BINDINGS = [
        Binding("n", "switch_tab('tab-navigator')", "Navigator"),
        Binding("s", "switch_tab('tab-status')", "Status"),
        Binding("h", "switch_tab('tab-health')", "Health"),
        Binding("f", "toggle_health_filter", "Toggle health filter", show=False),
        Binding("S", "show_secrets", "Secrets", show=False),
        Binding("O", "show_offers", "Offers", show=False),
        Binding("C", "show_settings", "Settings", show=False),
        Binding("L", "show_logs", "Logs", show=False),
        Binding("r", "refresh_data", "Refresh"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    _TAB_FOCUS_MAP = {
        "tab-navigator": "#clouds-table",
        "tab-status": "#status-apps-table DataTable",
        "tab-health": "#health-models-table",
    }

    def __init__(self, settings: AppSettings | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings or load_settings()
        self._poller: JujuPoller | None = None
        self._poll_timer: Timer | None = None
        # Full data stores — refreshed on every poll
        self._all_clouds: list[CloudInfo] = []
        self._all_controllers: list[ControllerInfo] = []
        self._all_models: list[ModelInfo] = []
        self._all_apps: list[AppInfo] = []
        self._all_units: list[UnitInfo] = []
        self._all_relations: list[RelationInfo] = []
        self._all_offers: list[OfferInfo] = []
        self._all_saas: list[SAASInfo] = []
        self._all_machines: list[MachineInfo] = []
        self._all_storage: list[StorageInfo] = []
        # Connection state
        self._is_connected: bool = False
        self._last_refresh_ts: str = ""
        # Drill-down filter state
        self._selected_cloud: str | None = None
        self._selected_controller: str | None = None
        self._selected_model: str | None = None
        # Auto-select: populated from Juju config on startup, cleared after first use
        self._auto_select_model: str | None = None
        # Offers cache: keyed by controller name, value is (offers, fetch_timestamp).
        # Entries older than settings.offers_cache_ttl seconds are re-fetched.
        self._offers_cache: dict[str, tuple[list[ControllerOfferInfo], float]] = {}
        # App config cache: keyed by (controller, model, app_name).
        # Entries are kept until the user explicitly refreshes with 'r' inside the modal.
        self._app_config_cache: dict[tuple[str, str, str], list[AppConfigEntry]] = {}

    def compose(self) -> ComposeResult:
        yield JujuMateHeader(id="main-header")
        with TabbedContent(initial="tab-navigator"):
            with TabPane("Navigator", id="tab-navigator"):
                yield NavigatorView(id="navigator-view")
            with TabPane("Status", id="tab-status"):
                yield StatusView(id="status-view")
            with TabPane("Health", id="tab-health"):
                yield HealthView(id="health-view")

    def on_mount(self) -> None:
        self.run_worker(self._connect_and_poll(), exclusive=True)

    async def _connect_and_poll(self) -> None:
        try:
            juju_config = load_config(Path(self._settings.juju_data_dir))
        except JujuConfigError as e:
            self.post_message(ConnectionFailed(error=str(e)))
            return

        self._poller = JujuPoller(controller_names=juju_config.controllers, target=self)
        effective_controller = self._settings.default_controller or juju_config.current_controller
        if effective_controller:
            current_model = juju_config.controller_models.get(effective_controller)
            if current_model:
                self._auto_select_model = current_model
                logger.info(
                    "Will auto-select model '%s' on controller '%s' after first poll",
                    current_model,
                    effective_controller,
                )
        await self._poller.poll_once()
        self._poll_timer = self.set_interval(self._settings.refresh_interval, self._periodic_poll)

    async def _periodic_poll(self) -> None:
        """Timer callback: only poll if the Status or Health tab is currently active.

        On the Status tab with a model selected, uses a targeted single-model poll
        instead of a full poll across all controllers, reducing API calls significantly.
        Polling is skipped entirely when any modal is open (MainScreen is not the top screen).
        """
        if not self._poller:
            return
        if self.app.screen is not self:
            return
        active_tab = self.query_one(TabbedContent).active
        if active_tab == "tab-status" and self._selected_controller and self._selected_model:
            await self._poller.poll_model(self._selected_controller, self._selected_model)
        elif active_tab in ("tab-status", "tab-health"):
            await self._poller.poll_once()

    async def on_unmount(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()

    def action_switch_tab(self, tab_id: str) -> None:
        tc = self.query_one(TabbedContent)
        tc.active = tab_id
        self._refresh_header()
        if widget_id := self._TAB_FOCUS_MAP.get(tab_id):
            self.call_after_refresh(self.query_one(widget_id).focus)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._refresh_header()
        tab_id = (event.tab.id if event.tab else "") or ""
        if widget_id := self._TAB_FOCUS_MAP.get(tab_id):
            self.call_after_refresh(self.query_one(widget_id).focus)
        # Re-render the newly visible tab with current cached data (no new API call).
        # Use call_after_refresh so the tab pane is fully mounted before populating.
        if tab_id == "tab-status":
            self.call_after_refresh(self._refresh_status_view)
        elif tab_id == "tab-health":
            self.call_after_refresh(self._refresh_health_view)

    def _active_tab(self) -> str:
        """Return the id of the currently active tab (empty string if not mounted yet)."""
        try:
            return self.query_one(TabbedContent).active or ""
        except NoMatches:
            return ""

    async def action_refresh_data(self) -> None:
        self.notify("Refreshing…")
        if self._poller:
            await self._poller.poll_once()
        logger.info("Manual refresh triggered")

    def action_clear_filter(self) -> None:
        # When a model is selected the cloud/controller/model form a coherent navigation
        # state driven by the Status tab. Esc should not disrupt that state.
        if self._selected_model is not None:
            return
        self._selected_cloud = None
        self._selected_controller = None
        self.query_one("#navigator-view", NavigatorView).reset_selection()
        self._refresh_header()
        self.notify("Filter cleared")

    def action_quit(self) -> None:
        self.app.exit()

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_show_secrets(self) -> None:
        if not self._selected_controller or not self._selected_model:
            self.notify("Select a model first", severity="warning")
            return
        self.app.push_screen(SecretsScreen(self._selected_controller, self._selected_model))

    def action_show_offers(self) -> None:
        if not self._selected_controller:
            self.notify("Select a controller first", severity="warning")
            return
        ctrl = self._selected_controller
        cached_entry = self._offers_cache.get(ctrl)
        if cached_entry is not None:
            offers, ts = cached_entry
            if time.monotonic() - ts <= self._settings.offers_cache_ttl:
                prefetched: list[ControllerOfferInfo] | None = offers
            else:
                prefetched = None
        else:
            prefetched = None

        def _on_fetched(offers: list[ControllerOfferInfo]) -> None:
            self._offers_cache[ctrl] = (offers, time.monotonic())

        self.app.push_screen(
            OffersScreen(
                ctrl,
                prefetched=prefetched,
                on_fetched=_on_fetched,
                all_saas=self._all_saas,
            )
        )

    def action_show_settings(self) -> None:
        controller_names = [c.name for c in self._all_controllers]

        def _apply(new_settings: AppSettings | None) -> None:
            if new_settings is None:
                return
            old_interval = self._settings.refresh_interval
            self._settings = new_settings
            if new_settings.refresh_interval != old_interval:
                if self._poll_timer is not None:
                    self._poll_timer.stop()
                self._poll_timer = self.set_interval(
                    new_settings.refresh_interval, self._periodic_poll
                )

        self.app.push_screen(SettingsScreen(self._settings, controller_names), _apply)

    def action_show_logs(self) -> None:
        if not self._selected_controller or not self._selected_model:
            self.notify("Select a model first", severity="warning")
            return
        self.app.push_screen(LogScreen(self._selected_controller, self._selected_model))

    def action_toggle_health_filter(self) -> None:
        if self._active_tab() == "tab-health":
            self.query_one("#health-view", HealthView).action_toggle_filter()

    # ── Filter helpers ────────────────────────────────────────────────────────

    def _refresh_navigator_view(self) -> None:
        nav = self.query_one("#navigator-view", NavigatorView)
        nav.update_controllers(self._all_controllers)
        nav.update_models(self._all_models)
        if self._selected_model and self._selected_controller:
            nav.select_model(self._selected_controller, self._selected_model)

    def _filter_by_model(self, items: list[_T]) -> list[_T]:
        """Return items whose .model matches the selected model (and .controller if set)."""
        if self._selected_model is None:
            return []
        ctrl = self._selected_controller
        return [
            x
            for x in items
            if x.model == self._selected_model and (not ctrl or x.controller == ctrl)  # type: ignore[attr-defined]
        ]

    def _is_kubernetes_model(self) -> bool:
        """Return True if the currently selected model is a Kubernetes model."""
        if self._selected_model is None:
            return False
        ctrl = self._selected_controller
        model_info = next(
            (
                m
                for m in self._all_models
                if m.name == self._selected_model and (not ctrl or m.controller == ctrl)
            ),
            None,
        )
        return model_info.is_kubernetes if model_info else False

    def _refresh_status_view(self) -> None:
        apps = self._filter_by_model(self._all_apps)
        units = self._filter_by_model(self._all_units)
        machines = self._filter_by_model(self._all_machines)
        relations = self._filter_by_model(self._all_relations)
        offers = self._filter_by_model(self._all_offers)
        saas = self._filter_by_model(self._all_saas)
        storage = self._filter_by_model(self._all_storage)
        is_kubernetes = self._is_kubernetes_model()

        status_view = self.query_one("#status-view", StatusView)
        status_view.update_context(
            cloud=self._effective_cloud() or "",
            controller=self._selected_controller or "",
            model=self._selected_model or "",
            juju_version=next(
                (
                    c.juju_version
                    for c in self._all_controllers
                    if c.name == self._selected_controller
                ),
                "",
            ),
        )
        status_view.update_apps(apps)
        status_view.update_units(units, is_kubernetes=is_kubernetes)
        status_view.update_machines(machines, is_kubernetes=is_kubernetes)
        status_view.update_saas(saas)
        status_view.update_offers(offers)
        status_view.update_relations(relations)
        status_view.update_storage(storage)

    def _refresh_health_view(self) -> None:
        self.query_one("#health-view", HealthView).update(
            self._all_models,
            self._all_apps,
            self._all_units,
        )

    def _effective_cloud(self) -> str | None:
        """Return the effective cloud: explicit selection, or derived from the selected model."""
        if self._selected_cloud:
            return self._selected_cloud
        if self._selected_model:
            ctrl = self._selected_controller
            model_info = next(
                (
                    m
                    for m in self._all_models
                    if m.name == self._selected_model and (not ctrl or m.controller == ctrl)
                ),
                None,
            )
            if model_info:
                return model_info.cloud
        return None

    def _refresh_header(self) -> None:
        try:
            header = self.query_one("#main-header", JujuMateHeader)
            active_tab = self.query_one(TabbedContent).active
        except NoMatches:
            return  # Not fully mounted yet

        filtered_controllers = [
            c
            for c in self._all_controllers
            if self._selected_cloud is None or c.cloud == self._selected_cloud
        ]
        filtered_models = [
            m
            for m in self._all_models
            if self._selected_controller is None or m.controller == self._selected_controller
        ]
        ctx = HeaderContext(
            active_tab=active_tab,
            selected_cloud=self._effective_cloud(),
            selected_controller=self._selected_controller,
            selected_model=self._selected_model,
            cloud_count=len(self._all_clouds),
            controller_count=len(filtered_controllers),
            model_count=len(filtered_models),
            app_count=len(self._filter_by_model(self._all_apps)),
            unit_count=len(self._filter_by_model(self._all_units)),
            offer_count=len(self._filter_by_model(self._all_offers)),
            relation_count=len(self._filter_by_model(self._all_relations)),
            saas_count=len(self._filter_by_model(self._all_saas)),
            machine_count=len(self._filter_by_model(self._all_machines)),
            is_connected=self._is_connected,
            timestamp=self._last_refresh_ts,
            juju_version=next(
                (
                    c.juju_version
                    for c in self._all_controllers
                    if c.name == self._selected_controller
                ),
                "",
            ),
        )
        header.update_context(ctx)

    # ── Juju data message handlers ────────────────────────────────────────────

    def on_clouds_updated(self, message: CloudsUpdated) -> None:
        self._all_clouds = message.clouds
        self.query_one("#navigator-view", NavigatorView).update_clouds(message.clouds)
        self._refresh_header()

    def on_controllers_updated(self, message: ControllersUpdated) -> None:
        self._all_controllers = message.controllers
        self._refresh_navigator_view()
        self._refresh_header()

    def on_models_updated(self, message: ModelsUpdated) -> None:
        if message.model and message.controller:
            # Targeted update: replace only the matching model, keep the rest.
            self._all_models = [
                m
                for m in self._all_models
                if not (m.controller == message.controller and m.name == message.model)
            ] + message.models
        else:
            # Full poll: check for deleted models before replacing.
            existing = {(m.controller, m.name) for m in message.models}
            if (
                self._selected_model
                and (self._selected_controller, self._selected_model) not in existing
            ):
                self.app.notify(
                    f"Model '{self._selected_model}' no longer exists.",
                    title="Model removed",
                    severity="warning",
                )
                self._selected_model = None
                self.action_switch_tab("tab-navigator")

            # Prune stale relations / offers / SAAS for models that no longer exist.
            self._all_relations = [
                r for r in self._all_relations if (r.controller, r.model) in existing
            ]
            self._all_offers = [o for o in self._all_offers if (o.controller, o.model) in existing]
            self._all_saas = [s for s in self._all_saas if (s.controller, s.model) in existing]
            self._all_models = message.models

        self._refresh_navigator_view()
        active = self._active_tab()
        if active == "tab-status":
            self._refresh_status_view()
        elif active == "tab-health":
            self._refresh_health_view()
        self._refresh_header()

    def on_apps_updated(self, message: AppsUpdated) -> None:
        if message.model and message.controller:
            # Targeted update: replace only apps for this (controller, model) pair.
            self._all_apps = [
                a
                for a in self._all_apps
                if not (a.controller == message.controller and a.model == message.model)
            ] + message.apps
        else:
            self._all_apps = message.apps
        active = self._active_tab()
        if active == "tab-status":
            self._refresh_status_view()
        elif active == "tab-health":
            self._refresh_health_view()
        self._refresh_header()

    def on_units_updated(self, message: UnitsUpdated) -> None:
        if message.model and message.controller:
            # Targeted update: replace only units for this (controller, model) pair.
            self._all_units = [
                u
                for u in self._all_units
                if not (u.controller == message.controller and u.model == message.model)
            ] + message.units
        else:
            self._all_units = message.units
        active = self._active_tab()
        if active == "tab-status":
            self._refresh_status_view()
        elif active == "tab-health":
            self._refresh_health_view()
        self._refresh_header()

    def on_machines_updated(self, message: MachinesUpdated) -> None:
        if message.model and message.controller:
            # Targeted update: replace only machines for this (controller, model) pair.
            self._all_machines = [
                m
                for m in self._all_machines
                if not (m.controller == message.controller and m.model == message.model)
            ] + message.machines
        else:
            self._all_machines = message.machines
        if self._active_tab() == "tab-status":
            self._refresh_status_view()

    def on_relations_updated(self, message: RelationsUpdated) -> None:
        # Replace relations for this (controller, model) pair (keep other models' relations intact)
        self._all_relations = [
            r
            for r in self._all_relations
            if not (r.model == message.model and r.controller == message.controller)
        ] + message.relations
        if self._active_tab() == "tab-status":
            self._refresh_status_view()
        self._refresh_header()
        logger.debug("Relations updated for model '%s': %d", message.model, len(message.relations))

    def on_offers_updated(self, message: OffersUpdated) -> None:
        # Replace offers for this (controller, model) pair (keep other models' offers intact)
        self._all_offers = [
            o
            for o in self._all_offers
            if not (o.model == message.model and o.controller == message.controller)
        ] + message.offers
        if self._active_tab() == "tab-status":
            self._refresh_status_view()
        self._refresh_header()
        logger.debug("Offers updated for model '%s': %d", message.model, len(message.offers))

    def on_saas_updated(self, message: SaasUpdated) -> None:
        # Replace SAAS for this (controller, model) pair (keep other models' SAAS intact)
        self._all_saas = [
            s
            for s in self._all_saas
            if not (s.model == message.model and s.controller == message.controller)
        ] + message.saas
        if self._active_tab() == "tab-status":
            self._refresh_status_view()
        logger.debug("SAAS updated for model '%s': %d", message.model, len(message.saas))

    def on_storage_updated(self, message: StorageUpdated) -> None:
        self._all_storage = [
            s
            for s in self._all_storage
            if not (s.model == message.model and s.controller == message.controller)
        ] + message.storage
        if self._active_tab() == "tab-status":
            self._refresh_status_view()
        logger.debug("Storage updated for model '%s': %d", message.model, len(message.storage))

    def on_data_refreshed(self, message: DataRefreshed) -> None:
        self._is_connected = True
        self._last_refresh_ts = message.timestamp.strftime("%H:%M:%S")
        self._refresh_header()
        if self._auto_select_model and self._selected_model is None:
            model_name = self._auto_select_model
            self._auto_select_model = None  # only once
            self._apply_auto_select(model_name)

    def _apply_auto_select(self, model_name: str) -> None:
        model_info = next((m for m in self._all_models if m.name == model_name), None)
        if model_info is None:
            logger.warning("Auto-select: model '%s' not found in loaded data", model_name)
            return
        self._selected_controller = model_info.controller
        self._selected_model = model_name
        self._refresh_navigator_view()
        self._refresh_status_view()
        self._refresh_header()
        self.action_switch_tab("tab-status")
        logger.info(
            "Auto-selected model '%s' on controller '%s'", model_name, model_info.controller
        )

    def on_connection_failed(self, message: ConnectionFailed) -> None:
        self._is_connected = False
        self._refresh_header()
        self.notify(f"Connection failed: {message.error}", severity="error")
        logger.error("Connection failed: %s", message.error)

    # ── Drill-down selection handlers ─────────────────────────────────────────

    def on_navigator_view_cloud_selected(self, message: NavigatorView.CloudSelected) -> None:
        self._selected_cloud = message.name
        self._selected_controller = None
        self._selected_model = None
        self._refresh_status_view()

    def on_navigator_view_controller_selected(
        self, message: NavigatorView.ControllerSelected
    ) -> None:
        self._selected_controller = message.name
        self._selected_model = None
        self._refresh_status_view()
        logger.debug(
            "Controller selected: '%s' → %d models (total stored: %d)",
            self._selected_controller,
            sum(1 for m in self._all_models if m.controller == self._selected_controller),
            len(self._all_models),
        )
        self._refresh_header()

    def on_navigator_view_model_selected(self, message: NavigatorView.ModelSelected) -> None:
        parts = message.name.split("/", 1)
        if len(parts) == 2:
            self._selected_controller = parts[0]
            self._selected_model = parts[1]
        else:
            self._selected_model = message.name
        if self._selected_controller:
            self._settings.default_controller = self._selected_controller
            save_settings(self._settings)
        self._refresh_status_view()
        self._refresh_header()
        self.action_switch_tab("tab-status")

    def on_health_view_model_drill_down(self, message: HealthView.ModelDrillDown) -> None:
        self._selected_controller = message.controller
        self._selected_model = message.model
        self._settings.default_controller = message.controller
        save_settings(self._settings)
        self._refresh_status_view()
        self._refresh_header()
        self.action_switch_tab("tab-status")

    def on_status_view_app_selected(self, message: StatusView.AppSelected) -> None:
        if not self._selected_controller or not self._selected_model:
            return
        cache_key = (self._selected_controller, self._selected_model, message.app.name)
        prefetched = self._app_config_cache.get(cache_key)

        def _on_fetched(entries: list[AppConfigEntry]) -> None:
            self._app_config_cache[cache_key] = entries

        self.app.push_screen(
            AppConfigScreen(
                self._selected_controller,
                self._selected_model,
                message.app,
                prefetched_entries=prefetched,
                on_fetched=_on_fetched,
            )
        )

    def on_status_view_relation_selected(self, message: StatusView.RelationSelected) -> None:
        relation = message.relation
        if not self._selected_controller or not relation.relation_id:
            return
        self.app.push_screen(
            RelationDataScreen(
                self._selected_controller,
                relation.model or self._selected_model or "",
                relation,
            )
        )

    def on_status_view_offer_selected(self, message: StatusView.OfferSelected) -> None:
        offer = message.offer
        if not self._selected_controller:
            return
        self._open_offer_detail(self._selected_controller, offer.model, offer.name)

    def on_status_view_machine_selected(self, message: StatusView.MachineSelected) -> None:
        self.app.push_screen(MachineDetailScreen(message.machine))

    def on_status_view_storage_selected(self, message: StatusView.StorageSelected) -> None:
        self.app.push_screen(StorageDetailScreen(message.storage))

    @work
    async def _open_offer_detail(
        self, controller_name: str, model_name: str, offer_name: str
    ) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                detail = await client.get_offer_detail(model_name, offer_name)
        except (JujuError, OSError, asyncio.TimeoutError, KeyError):
            logger.exception(
                "Failed to fetch offer detail for '%s' in model '%s'", offer_name, model_name
            )
            return
        if detail:
            self.app.push_screen(
                OfferDetailScreen(detail, controller_name, all_saas=self._all_saas)
            )
