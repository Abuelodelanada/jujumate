"""Modal screens for secrets list and secret detail."""

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label

from jujumate import palette
from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import SecretInfo

logger = logging.getLogger(__name__)


class SecretDetailScreen(ModalScreen):
    """Modal overlay showing full details of a single secret."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]

    DEFAULT_CSS = """
    SecretDetailScreen {
        align: center middle;
    }
    SecretDetailScreen #detail-panel {
        width: 70%;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    SecretDetailScreen #detail-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    SecretDetailScreen .detail-row {
        height: auto;
    }
    """

    def __init__(self, secret: SecretInfo) -> None:
        super().__init__()
        self._secret = secret

    def compose(self) -> ComposeResult:
        s = self._secret
        with Vertical(id="detail-panel"):
            yield Label(f"Secret — {s.label or s.uri}", id="detail-title")
            for field, value in [
                ("URI", s.uri),
                ("Label", s.label or "—"),
                ("Owner", s.owner or "—"),
                ("Revision", str(s.revision)),
                ("Rotation policy", s.rotate_policy or "—"),
                ("Created", s.created or "—"),
                ("Updated", s.updated or "—"),
                ("Description", s.description or "—"),
            ]:
                yield Label(f"[bold]{field}:[/bold]  {value}", classes="detail-row")


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
    SecretsScreen #secrets-loading {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    SecretsScreen DataTable {
        height: 1fr;
    }
    """

    def __init__(self, controller_name: str, model_name: str) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name
        self._secrets: list[SecretInfo] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="secrets-panel"):
            yield Label(f"Secrets — {self._model_name}", id="secrets-title")
            yield Label("Loading…", id="secrets-loading")
            yield DataTable(id="secrets-table", show_cursor=True, cursor_type="row")

    def on_mount(self) -> None:
        dt = self.query_one("#secrets-table", DataTable)
        dt.add_columns("URI", "Label", "Owner", "Rev", "Rotation", "Description")
        dt.display = False
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
        self._secrets = secrets
        loading = self.query_one("#secrets-loading")
        loading.display = False
        dt = self.query_one("#secrets-table", DataTable)
        if not secrets:
            loading.update("No secrets found.")
            loading.display = True
            return
        for i, s in enumerate(secrets):
            dt.add_row(
                Text(s.uri, style=palette.LINK),
                s.label or "—",
                s.owner or "—",
                str(s.revision),
                s.rotate_policy or "—",
                s.description or "—",
                key=str(i),
            )
        dt.display = True

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(str(event.row_key.value))
        if 0 <= idx < len(self._secrets):
            self.app.push_screen(SecretDetailScreen(self._secrets[idx]))

    def _show_error(self, error: str) -> None:
        loading = self.query_one("#secrets-loading")
        loading.update(Text(f"Error: {error}", style="bold red"))
        loading.display = True
