import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

from jujumate.client.juju_client import JujuClient, JujuClientError
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
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: AppSettings | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings or load_settings()
        self._client: JujuClient | None = None
        self._poller: JujuPoller | None = None

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
        controller_name = self._settings.default_controller
        self._client = JujuClient(controller_name=controller_name)
        try:
            await self._client.connect()
        except JujuClientError as e:
            self.post_message(ConnectionFailed(error=str(e)))
            return

        self._poller = JujuPoller(client=self._client, target=self)
        await self._poller.poll_once()
        self.set_interval(self._settings.refresh_interval, self._poller.poll_once)

    async def on_unmount(self) -> None:
        if self._client:
            await self._client.disconnect()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    async def action_refresh_data(self) -> None:
        if self._poller:
            await self._poller.poll_once()
        logger.info("Manual refresh triggered")
        self.notify("Refreshing…")

    def action_quit(self) -> None:
        self.app.exit()

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_clouds_updated(self, message: CloudsUpdated) -> None:
        self.query_one("#clouds-view", CloudsView).update(message.clouds)

    def on_controllers_updated(self, message: ControllersUpdated) -> None:
        self.query_one("#controllers-view", ControllersView).update(message.controllers)

    def on_models_updated(self, message: ModelsUpdated) -> None:
        self.query_one("#models-view", ModelsView).update(message.models)

    def on_apps_updated(self, message: AppsUpdated) -> None:
        self.query_one("#apps-view", AppsView).update(message.apps)

    def on_units_updated(self, message: UnitsUpdated) -> None:
        self.query_one("#units-view", UnitsView).update(message.units)

    def on_data_refreshed(self, message: DataRefreshed) -> None:
        ts = message.timestamp.strftime("%H:%M:%S")
        self.app.sub_title = f"⣾ Live  ·  {ts}"
        logger.debug("Data refreshed at %s", ts)

    def on_connection_failed(self, message: ConnectionFailed) -> None:
        self.app.sub_title = "⚠ Disconnected"
        self.notify(f"Connection failed: {message.error}", severity="error")
        logger.error("Connection failed: %s", message.error)
