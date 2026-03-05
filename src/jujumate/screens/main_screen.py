import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
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
    UnitsUpdated,
)
from jujumate.config import JujuConfigError, load_config
from jujumate.models.entities import (
    AppInfo,
    CloudInfo,
    ControllerInfo,
    MachineInfo,
    ModelInfo,
    OfferInfo,
    RelationInfo,
    SAASInfo,
    UnitInfo,
)
from jujumate.screens.app_config_screen import AppConfigScreen
from jujumate.screens.help_screen import HelpScreen
from jujumate.screens.offers_screen import OfferDetailScreen, OffersScreen
from jujumate.screens.relation_data_screen import RelationDataScreen
from jujumate.screens.secrets_screen import SecretsScreen
from jujumate.screens.theme_screen import ThemeScreen
from jujumate.settings import AppSettings, load_settings
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.status_view import StatusView

logger = logging.getLogger(__name__)


class MainScreen(Screen):
    BINDINGS = [
        Binding("c", "switch_tab('tab-clouds')", "Clouds"),
        Binding("C", "switch_tab('tab-controllers')", "Controllers"),
        Binding("m", "switch_tab('tab-models')", "Models"),
        Binding("s", "switch_tab('tab-status')", "Status"),
        Binding("S", "show_secrets", "Secrets", show=False),
        Binding("O", "show_offers", "Offers", show=False),
        Binding("T", "show_themes", "Theme", show=False),
        Binding("r", "refresh_data", "Refresh"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

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
        # Connection state
        self._is_connected: bool = False
        self._last_refresh_ts: str = ""
        # Drill-down filter state
        self._selected_cloud: str | None = None
        self._selected_controller: str | None = None
        self._selected_model: str | None = None
        # Auto-select: populated from Juju config on startup, cleared after first use
        self._auto_select_model: str | None = None

    def compose(self) -> ComposeResult:
        yield JujuMateHeader(id="main-header")
        with TabbedContent(initial="tab-clouds"):
            with TabPane("Clouds", id="tab-clouds"):
                yield CloudsView(id="clouds-view")
            with TabPane("Controllers", id="tab-controllers"):
                yield ControllersView(id="controllers-view")
            with TabPane("Models", id="tab-models"):
                yield ModelsView(id="models-view")
            with TabPane("Status", id="tab-status"):
                yield StatusView(id="status-view")

    def on_mount(self) -> None:
        self.run_worker(self._connect_and_poll(), exclusive=True)

    async def _connect_and_poll(self) -> None:
        try:
            juju_config = load_config(Path(self._settings.juju_data_dir))
        except JujuConfigError as e:
            self.post_message(ConnectionFailed(error=str(e)))
            return

        self._poller = JujuPoller(controller_names=juju_config.controllers, target=self)
        if juju_config.current_model:
            self._auto_select_model = juju_config.current_model
            logger.info("Will auto-select model '%s' after first poll", juju_config.current_model)
        await self._poller.poll_once()
        self._poll_timer = self.set_interval(self._settings.refresh_interval, self._periodic_poll)

    async def _periodic_poll(self) -> None:
        """Timer callback: only poll if the Status tab is currently active."""
        if not self._poller:
            return
        active_tab = self.query_one(TabbedContent).active
        if active_tab == "tab-status":
            await self._poller.poll_once()
            if self._selected_controller and self._selected_model:
                self._fetch_relations(self._selected_controller, self._selected_model)

    async def on_unmount(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()

    def action_switch_tab(self, tab_id: str) -> None:
        tc = self.query_one(TabbedContent)
        tc.active = tab_id
        self._refresh_header()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._refresh_header()

    async def action_refresh_data(self) -> None:
        self.notify("Refreshing…")
        if self._poller:
            await self._poller.poll_once()
        if self._selected_controller and self._selected_model:
            self._fetch_relations(self._selected_controller, self._selected_model)
        logger.info("Manual refresh triggered")

    def action_clear_filter(self) -> None:
        # When a model is selected the cloud/controller/model form a coherent navigation
        # state driven by the Status tab. Esc should not disrupt that state.
        if self._selected_model is not None:
            return
        self._selected_cloud = None
        self._selected_controller = None
        self._refresh_controllers_view()
        self._refresh_models_view()
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
        self.app.push_screen(OffersScreen(self._selected_controller))

    def action_show_themes(self) -> None:
        self.app.push_screen(ThemeScreen())

    # ── Filter helpers ────────────────────────────────────────────────────────

    def _refresh_controllers_view(self) -> None:
        filtered = [
            c
            for c in self._all_controllers
            if self._selected_cloud is None or c.cloud == self._selected_cloud
        ]
        self.query_one("#controllers-view", ControllersView).update(filtered)

    def _refresh_models_view(self) -> None:
        filtered = [
            m
            for m in self._all_models
            if self._selected_controller is None or m.controller == self._selected_controller
        ]
        models_view = self.query_one("#models-view", ModelsView)
        models_view.update(filtered)
        if self._selected_model and self._selected_controller:
            models_view.select_model(self._selected_controller, self._selected_model)

    def _refresh_status_view(self) -> None:
        if self._selected_model is None:
            apps: list[AppInfo] = []
            units: list[UnitInfo] = []
            machines: list[MachineInfo] = []
            is_kubernetes = False
        else:
            apps = [a for a in self._all_apps if a.model == self._selected_model]
            {a.name for a in apps}
            units = [u for u in self._all_units if u.model == self._selected_model]
            machines = [m for m in self._all_machines if m.model == self._selected_model]
            model_info = next((m for m in self._all_models if m.name == self._selected_model), None)
            is_kubernetes = model_info.is_kubernetes if model_info else False
        relations = (
            [r for r in self._all_relations if r.model == self._selected_model]
            if self._selected_model
            else []
        )
        offers = (
            [o for o in self._all_offers if o.model == self._selected_model]
            if self._selected_model
            else []
        )
        saas = (
            [s for s in self._all_saas if s.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_view = self.query_one("#status-view", StatusView)
        status_view.update_apps(apps)
        status_view.update_units(units, is_kubernetes=is_kubernetes)
        status_view.update_machines(machines, is_kubernetes=is_kubernetes)
        status_view.update_saas(saas)
        status_view.update_offers(offers)
        status_view.update_relations(relations)

    def _refresh_header(self) -> None:
        try:
            header = self.query_one("#main-header", JujuMateHeader)
            active_tab = self.query_one(TabbedContent).active
        except Exception:
            return  # Not fully mounted yet
        # Filtered counts matching what each view displays
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
        status_offers = (
            [o for o in self._all_offers if o.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_relations = (
            [r for r in self._all_relations if r.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_saas = (
            [s for s in self._all_saas if s.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_machines = (
            [m for m in self._all_machines if m.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_apps = (
            [a for a in self._all_apps if a.model == self._selected_model]
            if self._selected_model
            else []
        )
        status_app_names = {a.name for a in status_apps}
        status_units = [u for u in self._all_units if u.app in status_app_names]
        # Derive cloud from selected model if not explicitly set
        effective_cloud = self._selected_cloud
        if not effective_cloud and self._selected_model:
            model_info = next((m for m in self._all_models if m.name == self._selected_model), None)
            if model_info:
                effective_cloud = model_info.cloud
        ctx = HeaderContext(
            active_tab=active_tab,
            selected_cloud=effective_cloud,
            selected_controller=self._selected_controller,
            selected_model=self._selected_model,
            cloud_count=len(self._all_clouds),
            controller_count=len(filtered_controllers),
            model_count=len(filtered_models),
            app_count=len(status_apps),
            unit_count=len(status_units),
            offer_count=len(status_offers),
            relation_count=len(status_relations),
            saas_count=len(status_saas),
            machine_count=len(status_machines),
            is_connected=self._is_connected,
            timestamp=self._last_refresh_ts,
        )
        header.update_context(ctx)

    # ── Juju data message handlers ────────────────────────────────────────────

    def on_clouds_updated(self, message: CloudsUpdated) -> None:
        self._all_clouds = message.clouds
        self.query_one("#clouds-view", CloudsView).update(message.clouds)
        self._refresh_header()

    def on_controllers_updated(self, message: ControllersUpdated) -> None:
        self._all_controllers = message.controllers
        self._refresh_controllers_view()
        self._refresh_header()

    def on_models_updated(self, message: ModelsUpdated) -> None:
        existing = {m.name for m in message.models}

        # If the currently selected model was deleted, notify and switch to Models tab.
        if self._selected_model and self._selected_model not in existing:
            self.app.notify(
                f"Model '{self._selected_model}' no longer exists.",
                title="Model removed",
                severity="warning",
            )
            self._selected_model = None
            self.action_switch_tab("tab-models")

        # Prune stale relations / offers / SAAS for models that no longer exist.
        self._all_relations = [r for r in self._all_relations if r.model in existing]
        self._all_offers = [o for o in self._all_offers if o.model in existing]
        self._all_saas = [s for s in self._all_saas if s.model in existing]

        self._all_models = message.models
        self._refresh_models_view()
        self._refresh_status_view()
        self._refresh_header()

    def on_apps_updated(self, message: AppsUpdated) -> None:
        self._all_apps = message.apps
        self._refresh_status_view()
        self._refresh_header()

    def on_units_updated(self, message: UnitsUpdated) -> None:
        self._all_units = message.units
        self._refresh_status_view()
        self._refresh_header()

    def on_machines_updated(self, message: MachinesUpdated) -> None:
        self._all_machines = message.machines
        self._refresh_status_view()

    def on_relations_updated(self, message: RelationsUpdated) -> None:
        # Replace relations for this model (keep other models' relations intact)
        self._all_relations = [
            r for r in self._all_relations if r.model != message.model
        ] + message.relations
        self._refresh_status_view()
        self._refresh_header()
        logger.debug("Relations updated for model '%s': %d", message.model, len(message.relations))

    def on_offers_updated(self, message: OffersUpdated) -> None:
        # Replace offers for this model (keep other models' offers intact)
        self._all_offers = [
            o for o in self._all_offers if o.model != message.model
        ] + message.offers
        self._refresh_status_view()
        self._refresh_header()
        logger.debug("Offers updated for model '%s': %d", message.model, len(message.offers))

    def on_saas_updated(self, message: SaasUpdated) -> None:
        # Replace SAAS for this model (keep other models' SAAS intact)
        self._all_saas = [s for s in self._all_saas if s.model != message.model] + message.saas
        self._refresh_status_view()
        logger.debug("SAAS updated for model '%s': %d", message.model, len(message.saas))

    def on_data_refreshed(self, message: DataRefreshed) -> None:
        self._is_connected = True
        self._last_refresh_ts = message.timestamp.strftime("%H:%M:%S")
        self._refresh_header()
        if self._auto_select_model and self._selected_model is None:
            model_name = self._auto_select_model
            self._auto_select_model = None  # only once
            self._apply_auto_select(model_name)
        logger.debug("Data refreshed at %s", self._last_refresh_ts)

    def _apply_auto_select(self, model_name: str) -> None:
        model_info = next((m for m in self._all_models if m.name == model_name), None)
        if model_info is None:
            logger.warning("Auto-select: model '%s' not found in loaded data", model_name)
            return
        self._selected_controller = model_info.controller
        self._selected_model = model_name
        self._refresh_models_view()
        self._refresh_status_view()
        self._fetch_relations(self._selected_controller, self._selected_model)
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

    def on_clouds_view_cloud_selected(self, message: CloudsView.CloudSelected) -> None:
        self._selected_cloud = message.name
        self._selected_controller = None
        self._selected_model = None
        self._refresh_controllers_view()
        self._refresh_models_view()
        self._refresh_status_view()
        self.action_switch_tab("tab-controllers")

    def on_controllers_view_controller_selected(
        self, message: ControllersView.ControllerSelected
    ) -> None:
        self._selected_controller = message.name
        self._selected_model = None
        self._refresh_models_view()
        self._refresh_status_view()
        filtered_count = sum(
            1 for m in self._all_models if m.controller == self._selected_controller
        )
        logger.debug(
            "Controller selected: '%s' → %d models (total stored: %d, controllers in models: %s)",
            self._selected_controller,
            filtered_count,
            len(self._all_models),
            list({m.controller for m in self._all_models}),
        )
        self._refresh_header()
        self.action_switch_tab("tab-models")

    def on_models_view_model_selected(self, message: ModelsView.ModelSelected) -> None:
        # message.name is "controller/modelname"
        parts = message.name.split("/", 1)
        if len(parts) == 2:
            self._selected_controller = parts[0]
            self._selected_model = parts[1]
        else:
            self._selected_model = message.name
        self._refresh_status_view()
        if self._selected_controller:
            self._fetch_relations(self._selected_controller, self._selected_model)
        self._refresh_header()
        self.action_switch_tab("tab-status")

    @work(exclusive=True)
    async def _fetch_relations(self, controller_name: str, model_name: str) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                relations, offers, saas = await client.get_status_details(model_name)
            logger.debug(
                "Fetched %d relations, %d offers, %d saas for model '%s'",
                len(relations),
                len(offers),
                len(saas),
                model_name,
            )
            self.post_message(RelationsUpdated(model=model_name, relations=relations))
            self.post_message(OffersUpdated(model=model_name, offers=offers))
            self.post_message(SaasUpdated(model=model_name, saas=saas))
        except Exception:
            logger.exception("Failed to fetch status details for model '%s'", model_name)

    def on_status_view_app_selected(self, message: StatusView.AppSelected) -> None:
        if not self._selected_controller or not self._selected_model:
            return
        self.app.push_screen(
            AppConfigScreen(self._selected_controller, self._selected_model, message.app)
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

    @work
    async def _open_offer_detail(
        self, controller_name: str, model_name: str, offer_name: str
    ) -> None:
        async with JujuClient(controller_name=controller_name) as client:
            detail = await client.get_offer_detail(model_name, offer_name)
        if detail:
            self.app.push_screen(OfferDetailScreen(detail, controller_name))
