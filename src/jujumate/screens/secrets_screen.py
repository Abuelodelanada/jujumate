"""Modal screen showing all secrets for the selected model."""

import logging

from rich import box as rich_box
from rich.table import Table
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import SecretInfo

logger = logging.getLogger(__name__)

_HEADER_COLOR = "#E95420"


class SecretsScreen(ModalScreen):
    """Modal overlay displaying all secrets for a model."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]

    DEFAULT_CSS = """
    SecretsScreen {
        align: center middle;
    }
    SecretsScreen #secrets-panel {
        width: 90%;
        height: 85%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    SecretsScreen #secrets-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    SecretsScreen #secrets-body {
        height: 1fr;
        scrollbar-size-vertical: 0;
    }
    SecretsScreen #secrets-loading {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, controller_name: str, model_name: str) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="secrets-panel"):
            yield Label(f"Secrets — {self._model_name}", id="secrets-title")
            yield Label("Loading…", id="secrets-loading")
            yield Static("", id="secrets-body")

    def on_mount(self) -> None:
        self.query_one("#secrets-body").display = False
        self._fetch(self._controller_name, self._model_name)

    @work
    async def _fetch(self, controller_name: str, model_name: str) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                secrets = await client.get_secrets(model_name)
            self._populate(secrets)
        except Exception as exc:
            logger.exception("Failed to fetch secrets for model '%s'", model_name)
            self._show_error(str(exc))

    def _populate(self, secrets: list[SecretInfo]) -> None:
        self.query_one("#secrets-loading").display = False
        body = self.query_one("#secrets-body", Static)
        if not secrets:
            body.update(Text("No secrets found.", style="dim italic"))
            body.display = True
            return

        t = Table(
            box=rich_box.SIMPLE_HEAD,
            show_header=True,
            expand=True,
            header_style=f"bold {_HEADER_COLOR}",
            border_style="dim",
            padding=(0, 1, 1, 1),
        )
        t.add_column("URI")
        t.add_column("Label", width=20)
        t.add_column("Owner", width=20)
        t.add_column("Rev", width=5)
        t.add_column("Rotation", width=12)
        t.add_column("Description")

        for s in secrets:
            t.add_row(
                Text(s.uri, style="#19B6EE"),
                s.label or "—",
                s.owner or "—",
                str(s.revision),
                s.rotate_policy or "—",
                s.description or "—",
            )

        body.update(t)
        body.display = True

    def _show_error(self, error: str) -> None:
        self.query_one("#secrets-loading").display = False
        body = self.query_one("#secrets-body", Static)
        body.update(Text(f"Error: {error}", style="bold red"))
        body.display = True
