import logging

from textual.app import App

from jujumate.screens.main_screen import MainScreen

logger = logging.getLogger(__name__)


class JujuMateApp(App):
    TITLE = "JujuMate"
    SUB_TITLE = "Juju infrastructure at a glance"

    CSS = """
    $ubuntu-orange: #E95420;
    $aubergine-dark: #2C001E;
    $aubergine-mid: #5E2750;
    $aubergine-light: #77216F;
    $warm-grey: #AEA79F;

    Screen {
        background: $aubergine-dark;
    }

    Header {
        background: $aubergine-mid;
        color: white;
    }

    Footer {
        background: $aubergine-dark;
        color: $warm-grey;
    }

    TabbedContent > TabPane {
        background: $aubergine-dark;
    }

    Tabs {
        background: $aubergine-mid;
    }

    Tab {
        color: $warm-grey;
    }

    Tab:focus, Tab.-active {
        color: white;
        background: $ubuntu-orange;
    }

    Tab:hover {
        color: white;
        background: $aubergine-light;
    }
    """

    def on_mount(self) -> None:
        logger.info("JujuMate started")
        self.push_screen(MainScreen())
