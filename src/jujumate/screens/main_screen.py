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
    RelationDataFetchError,
    RelationDataUpdated,
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
from jujumate.screens.help_screen import HelpScreen
from jujumate.settings import AppSettings, load_settings
from jujumate.widgets.apps_view import AppsView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.relation_data_view import RelationDataView
from jujumate.widgets.status_view import StatusView
from jujumate.widgets.units_view import UnitsView

logger = logging.getLogger(__name__)


class MainScreen(Screen):
    BINDINGS = [
        Binding("c", "switch_tab('tab-clouds')", "Clouds"),
        Binding("C", "switch_tab('tab-controllers')", "Controllers"),
        Binding("m", "switch_tab('tab-models')", "Models"),
        Binding("s", "switch_tab('tab-status')", "Status"),
        Binding("a", "switch_tab('tab-apps')", "Apps"),
        Binding("u", "switch_tab('tab-units')", "Units"),
        Binding("d", "switch_tab('tab-relation-data')", "Rel. Data", show=False),
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
        self._selected_app: str | None = None
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
            with TabPane("Apps", id="tab-apps"):
                yield AppsView(id="apps-view")
            with TabPane("Units", id="tab-units"):
                yield UnitsView(id="units-view")
            with TabPane("Relation Data", id="tab-relation-data"):
                yield RelationDataView(id="relation-data-view")

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
        self._poll_timer = self.set_interval(
            self._settings.refresh_interval, self._periodic_poll
        )

    async def _periodic_poll(self) -> None:
        """Timer callback: only poll if the Status tab is currently active."""
        if not self._poller:
            return
        active_tab = self.query_one(TabbedContent).active
        if active_tab == "tab-status":
            await self._poller.poll_once()

    async def on_unmount(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
        self._refresh_header()

    async def action_refresh_data(self) -> None:
        if self._poller:
            await self._poller.poll_once()
        logger.info("Manual refresh triggered")
        self.notify("Refreshing…")

    def action_clear_filter(self) -> None:
        self._selected_cloud = None
        self._selected_controller = None
        self._selected_model = None
        self._selected_app = None
        self._refresh_controllers_view()
        self._refresh_models_view()
        self._refresh_apps_view()
        self._refresh_units_view()
        self._refresh_status_view()
        self._refresh_header()
        self.notify("Filter cleared — showing all resources")

    def action_quit(self) -> None:
        self.app.exit()

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

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
        self.query_one("#models-view", ModelsView).update(filtered)

    def _refresh_apps_view(self) -> None:
        filtered = [
            a
            for a in self._all_apps
            if self._selected_model is None or a.model == self._selected_model
        ]
        self.query_one("#apps-view", AppsView).update(filtered)

    def _refresh_units_view(self) -> None:
        filtered = [
            u for u in self._all_units if self._selected_app is None or u.app == self._selected_app
        ]
        self.query_one("#units-view", UnitsView).update(filtered)

    def _refresh_status_view(self) -> None:
        if self._selected_model is None:
            apps: list[AppInfo] = []
            units: list[UnitInfo] = []
            machines: list[MachineInfo] = []
            is_kubernetes = False
        else:
            apps = [a for a in self._all_apps if a.model == self._selected_model]
            app_names = {a.name for a in apps}
            units = [u for u in self._all_units if u.model == self._selected_model]
            machines = [
                m for m in self._all_machines
                if m.model == self._selected_model
            ]
            model_info = next(
                (m for m in self._all_models if m.name == self._selected_model), None
            )
            is_kubernetes = model_info.is_kubernetes if model_info else False
        relations = [
            r for r in self._all_relations if r.model == self._selected_model
        ] if self._selected_model else []
        offers = [
            o for o in self._all_offers if o.model == self._selected_model
        ] if self._selected_model else []
        saas = [
            s for s in self._all_saas if s.model == self._selected_model
        ] if self._selected_model else []
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
            c for c in self._all_controllers
            if self._selected_cloud is None or c.cloud == self._selected_cloud
        ]
        filtered_models = [
            m for m in self._all_models
            if self._selected_controller is None or m.controller == self._selected_controller
        ]
        filtered_apps = [
            a for a in self._all_apps
            if self._selected_model is None or a.model == self._selected_model
        ]
        filtered_units = [
            u for u in self._all_units
            if self._selected_app is None or u.app == self._selected_app
        ]
        status_offers = [o for o in self._all_offers if o.model == self._selected_model] if self._selected_model else []
        status_relations = [r for r in self._all_relations if r.model == self._selected_model] if self._selected_model else []
        status_apps = [a for a in self._all_apps if a.model == self._selected_model] if self._selected_model else []
        status_app_names = {a.name for a in status_apps}
        status_units = [u for u in self._all_units if u.app in status_app_names]
        ctx = HeaderContext(
            active_tab=active_tab,
            selected_cloud=self._selected_cloud,
            selected_controller=self._selected_controller,
            selected_model=self._selected_model,
            selected_app=self._selected_app,
            cloud_count=len(self._all_clouds),
            controller_count=len(filtered_controllers),
            model_count=len(filtered_models),
            app_count=len(status_apps) if active_tab == "tab-status" else len(filtered_apps),
            unit_count=len(status_units) if active_tab == "tab-status" else len(filtered_units),
            offer_count=len(status_offers),
            relation_count=len(status_relations),
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
        self._all_models = message.models
        self._refresh_models_view()
        self._refresh_header()

    def on_apps_updated(self, message: AppsUpdated) -> None:
        self._all_apps = message.apps
        self._refresh_apps_view()
        self._refresh_status_view()
        self._refresh_header()

    def on_units_updated(self, message: UnitsUpdated) -> None:
        self._all_units = message.units
        self._refresh_units_view()
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
        self._all_saas = [
            s for s in self._all_saas if s.model != message.model
        ] + message.saas
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
        self._refresh_apps_view()
        self._refresh_units_view()
        self._refresh_status_view()
        self._fetch_relations(self._selected_controller, self._selected_model)
        self._refresh_header()
        self.action_switch_tab("tab-status")
        logger.info("Auto-selected model '%s' on controller '%s'", model_name, model_info.controller)

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
        self._selected_app = None
        self._refresh_controllers_view()
        self._refresh_models_view()
        self._refresh_apps_view()
        self._refresh_units_view()
        self.action_switch_tab("tab-controllers")

    def on_controllers_view_controller_selected(
        self, message: ControllersView.ControllerSelected
    ) -> None:
        self._selected_controller = message.name
        self._selected_model = None
        self._selected_app = None
        self._refresh_models_view()
        self._refresh_apps_view()
        self._refresh_units_view()
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
        # message.name is "controller/modelname" — extract just the model name
        self._selected_model = message.name.split("/", 1)[-1]
        self._selected_app = None
        self._refresh_apps_view()
        self._refresh_units_view()
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
                len(relations), len(offers), len(saas), model_name,
            )
            self.post_message(RelationsUpdated(model=model_name, relations=relations))
            self.post_message(OffersUpdated(model=model_name, offers=offers))
            self.post_message(SaasUpdated(model=model_name, saas=saas))
        except Exception:
            logger.exception("Failed to fetch status details for model '%s'", model_name)

    def on_apps_view_app_selected(self, message: AppsView.AppSelected) -> None:
        # message.name is "model/appname" — extract just the app name
        self._selected_app = message.name.split("/", 1)[-1]
        self._refresh_units_view()
        self._refresh_header()
        self.action_switch_tab("tab-units")

    def on_status_view_relation_selected(self, message: StatusView.RelationSelected) -> None:
        """User pressed Enter on a relation — fetch its data bags and switch tab."""
        relation = message.relation
        if not self._selected_controller or not relation.relation_id:
            return
        self.query_one("#relation-data-view", RelationDataView).show_loading(relation)
        self.action_switch_tab("tab-relation-data")
        provider_app = relation.provider.split(":")[0]
        requirer_app = relation.requirer.split(":")[0]
        self._fetch_relation_data(
            self._selected_controller,
            relation.model or self._selected_model or "",
            relation,
            provider_app,
            requirer_app,
        )

    @work(exclusive=True)
    async def _fetch_relation_data(
        self,
        controller_name: str,
        model_name: str,
        relation: RelationInfo,
        provider_app: str,
        requirer_app: str,
    ) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                entries = await client.get_relation_data(
                    model_name, relation.relation_id, provider_app, requirer_app
                )
            logger.debug(
                "Fetched relation data for relation %d: %d entries",
                relation.relation_id, len(entries),
            )
            self.post_message(RelationDataUpdated(relation=relation, entries=entries))
        except Exception as exc:
            logger.exception(
                "Failed to fetch relation data for relation %d", relation.relation_id
            )
            self.post_message(RelationDataFetchError(relation=relation, error=str(exc)))

    def on_relation_data_updated(self, message: RelationDataUpdated) -> None:
        self.query_one("#relation-data-view", RelationDataView).update(
            message.relation, message.entries
        )

    def on_relation_data_fetch_error(self, message: RelationDataFetchError) -> None:
        self.query_one("#relation-data-view", RelationDataView).show_error(
            message.relation, message.error
        )
