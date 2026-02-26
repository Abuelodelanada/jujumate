import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Header, TabbedContent, TabPane

from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    ControllersUpdated,
    DataRefreshed,
    JujuPoller,
    ModelsUpdated,
    UnitsUpdated,
)
from jujumate.config import JujuConfigError, load_config
from jujumate.models.entities import AppInfo, ControllerInfo, ModelInfo, UnitInfo
from jujumate.settings import AppSettings, load_settings
from jujumate.widgets.apps_view import AppsView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.units_view import UnitsView

logger = logging.getLogger(__name__)


class MainScreen(Screen):
    BINDINGS = [
        Binding("c", "switch_tab('tab-clouds')", "Clouds"),
        Binding("C", "switch_tab('tab-controllers')", "Controllers"),
        Binding("m", "switch_tab('tab-models')", "Models"),
        Binding("a", "switch_tab('tab-apps')", "Apps"),
        Binding("u", "switch_tab('tab-units')", "Units"),
        Binding("r", "refresh_data", "Refresh"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: AppSettings | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings or load_settings()
        self._poller: JujuPoller | None = None
        self._poll_timer: Timer | None = None
        # Full data stores — refreshed on every poll
        self._all_controllers: list[ControllerInfo] = []
        self._all_models: list[ModelInfo] = []
        self._all_apps: list[AppInfo] = []
        self._all_units: list[UnitInfo] = []
        # Drill-down filter state
        self._selected_cloud: str | None = None
        self._selected_controller: str | None = None
        self._selected_model: str | None = None
        self._selected_app: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="tab-clouds"):
            with TabPane("Clouds", id="tab-clouds"):
                yield CloudsView(id="clouds-view")
            with TabPane("Controllers", id="tab-controllers"):
                yield ControllersView(id="controllers-view")
            with TabPane("Models", id="tab-models"):
                yield ModelsView(id="models-view")
            with TabPane("Apps", id="tab-apps"):
                yield AppsView(id="apps-view")
            with TabPane("Units", id="tab-units"):
                yield UnitsView(id="units-view")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._connect_and_poll(), exclusive=True)

    async def _connect_and_poll(self) -> None:
        try:
            juju_config = load_config(Path(self._settings.juju_data_dir))
        except JujuConfigError as e:
            self.post_message(ConnectionFailed(error=str(e)))
            return

        self._poller = JujuPoller(controller_names=juju_config.controllers, target=self)
        await self._poller.poll_once()
        self._poll_timer = self.set_interval(
            self._settings.refresh_interval, self._poller.poll_once
        )

    async def on_unmount(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

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
        self.notify("Filter cleared — showing all resources")

    def action_quit(self) -> None:
        self.app.exit()

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

    # ── Juju data message handlers ────────────────────────────────────────────

    def on_clouds_updated(self, message: CloudsUpdated) -> None:
        self.query_one("#clouds-view", CloudsView).update(message.clouds)

    def on_controllers_updated(self, message: ControllersUpdated) -> None:
        self._all_controllers = message.controllers
        self._refresh_controllers_view()

    def on_models_updated(self, message: ModelsUpdated) -> None:
        self._all_models = message.models
        self._refresh_models_view()

    def on_apps_updated(self, message: AppsUpdated) -> None:
        self._all_apps = message.apps
        self._refresh_apps_view()

    def on_units_updated(self, message: UnitsUpdated) -> None:
        self._all_units = message.units
        self._refresh_units_view()

    def on_data_refreshed(self, message: DataRefreshed) -> None:
        ts = message.timestamp.strftime("%H:%M:%S")
        self.app.sub_title = f"⣾ Live  ·  {ts}"
        logger.debug("Data refreshed at %s", ts)

    def on_connection_failed(self, message: ConnectionFailed) -> None:
        self.app.sub_title = "⚠ Disconnected"
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
        self.action_switch_tab("tab-models")

    def on_models_view_model_selected(self, message: ModelsView.ModelSelected) -> None:
        # message.name is "controller/modelname" — extract just the model name
        self._selected_model = message.name.split("/", 1)[-1]
        self._selected_app = None
        self._refresh_apps_view()
        self._refresh_units_view()
        self.action_switch_tab("tab-apps")

    def on_apps_view_app_selected(self, message: AppsView.AppSelected) -> None:
        # message.name is "model/appname" — extract just the app name
        self._selected_app = message.name.split("/", 1)[-1]
        self._refresh_units_view()
        self.action_switch_tab("tab-units")
