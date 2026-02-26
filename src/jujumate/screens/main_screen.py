import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

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
                yield Label("Clouds — coming soon")
            with TabPane("Controllers", id="tab-controllers"):
                yield Label("Controllers — coming soon")
            with TabPane("Models", id="tab-models"):
                yield Label("Models — coming soon")
            with TabPane("Apps", id="tab-apps"):
                yield Label("Applications — coming soon")
            with TabPane("Units", id="tab-units"):
                yield Label("Units — coming soon")
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh_data(self) -> None:
        logger.info("Manual refresh triggered")
        self.notify("Refreshing…")

    def action_quit(self) -> None:
        self.app.exit()
