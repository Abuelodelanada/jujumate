import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen

from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import AppInfo
from jujumate.widgets.app_config_view import AppConfigView

logger = logging.getLogger(__name__)


class AppConfigScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", show=False)]
    DEFAULT_CSS = (Path(__file__).parent / "app_config_screen.tcss").read_text()

    def __init__(self, controller_name: str, model_name: str, app: AppInfo) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name
        self._app = app

    def compose(self) -> ComposeResult:
        yield AppConfigView(id="app-config-view")

    def on_mount(self) -> None:
        view = self.query_one(AppConfigView)
        view.border_title = f"Config — {self._app.name}"
        view.show_loading(self._app)
        self._fetch(self._controller_name, self._model_name, self._app)

    @work
    async def _fetch(self, controller_name: str, model_name: str, app: AppInfo) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                entries = await client.get_app_config(model_name, app.name)
            self.query_one(AppConfigView).update(app, entries)
        except Exception as exc:
            logger.exception("Failed to fetch config for app '%s'", app.name)
            self.query_one(AppConfigView).show_error(app, str(exc))
