import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

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

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh_data(self) -> None:
        logger.info("Manual refresh triggered")
        self.notify("Refreshing…")

    def action_quit(self) -> None:
        self.app.exit()
