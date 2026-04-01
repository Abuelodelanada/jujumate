"""Modal screens for secrets list and secret detail."""

import asyncio
import logging
from pathlib import Path

from juju.errors import JujuError
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, ListItem, ListView, Rule, Static

from jujumate import palette
from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import SecretInfo

logger = logging.getLogger(__name__)


class SecretDetailScreen(ModalScreen):
    """Modal overlay showing full details and content of a single secret."""

    BINDINGS = [
        Binding("escape", "dismiss", show=False),
        Binding("y", "copy_value", "Copy value", show=False),
    ]

    _MASK = "••••••••"

    DEFAULT_CSS = (Path(__file__).parent / "secrets_screen.tcss").read_text()

    def __init__(
        self,
        controller_name: str,
        model_name: str,
        secret: SecretInfo,
        prefetched_content: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name
        self._secret = secret
        self._content_data: dict[str, str] = {}
        self._prefetched_content = prefetched_content

    def on_mount(self) -> None:
        s = self._secret
        self.query_one("#detail-panel").border_title = f"Secret — {s.label or s.uri}"
        self.query_one("#secret-data").display = False
        if self._prefetched_content is not None:
            self._content_data = self._prefetched_content
            lv = self.query_one("#secret-data", ListView)
            self._populate_list(lv, self._prefetched_content)
            self.query_one("#secret-loading").display = False
            lv.display = True
            lv.focus()
        else:
            self._fetch(self._controller_name, self._model_name, s.uri)

    def compose(self) -> ComposeResult:
        s = self._secret
        fields = [
            ("URI", s.uri),
            ("Label", s.label or "—"),
            ("Owner", s.owner or "—"),
            ("Revision", str(s.revision)),
            ("Rotation policy", s.rotate_policy or "—"),
            ("Created", s.created or "—"),
            ("Updated", s.updated or "—"),
            ("Description", s.description or "—"),
        ]
        col_width = max(len(f) for f, _ in fields) + 2
        with Vertical(id="detail-panel"):
            for field, value in fields:
                label = f"{field}:".ljust(col_width)
                yield Label(f"[bold]{label}[/bold]{value}", classes="detail-row")
            yield Rule()
            yield Label("Loading content…", id="secret-loading")
            yield ListView(id="secret-data")
            yield Label("<up> & <down>: select secret - y: copy to clipboard", id="secret-hint")

    def _populate_list(self, lv: ListView, data: dict[str, str]) -> None:
        """Populate the secret key-value ListView, or show an empty placeholder."""
        if not data:
            lv.append(ListItem(Label("[dim]<empty>[/dim]")))
            return
        keys = sorted(data.keys())
        col_width = max(len(k) for k in keys) + 2
        for k in keys:
            lv.append(
                ListItem(
                    Horizontal(
                        Label(f"[bold]{k.ljust(col_width)}[/bold]", classes="kv-key"),
                        Label(self._MASK, classes="kv-val masked"),
                    )
                )
            )

    @work
    async def _fetch(self, controller_name: str, model_name: str, secret_uri: str) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                data = await client.get_secret_content(model_name, secret_uri)
            self._content_data = data
            lv = self.query_one("#secret-data", ListView)
            self._populate_list(lv, data)
            self.query_one("#secret-loading").display = False
            lv.display = True
            lv.focus()
        except (JujuError, OSError, asyncio.TimeoutError, KeyError) as exc:
            logger.exception("Failed to fetch content for secret %s", secret_uri)
            self.query_one("#secret-loading", Label).update(f"[red]Error: {exc}[/red]")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        for item in self.query("#secret-data ListItem"):
            item.remove_class("kv-selected")
        if event.item:
            event.item.add_class("kv-selected")

    def action_copy_value(self) -> None:
        lv = self.query_one("#secret-data", ListView)
        if not lv.display or not self._content_data:
            return
        idx = lv.index
        if idx is not None:
            keys = sorted(self._content_data.keys())
            if 0 <= idx < len(keys):
                key = keys[idx]
                self.app.copy_to_clipboard(self._content_data[key])
                self.notify(f"Copied [bold]{key}[/bold] to clipboard")


class SecretsScreen(ModalScreen):
    """Modal overlay displaying all secrets for a model."""

    BINDINGS = [
        Binding("escape", "dismiss", show=False),
        Binding("r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = (Path(__file__).parent / "secrets_screen.tcss").read_text()

    def __init__(self, controller_name: str, model_name: str) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name
        self._secrets: list[SecretInfo] = []
        self._secret_contents: dict[str, dict[str, str]] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="secrets-panel"):
            yield Label("Loading…", id="secrets-loading")
            yield DataTable(id="secrets-table", show_cursor=True, cursor_type="row")

    def on_mount(self) -> None:
        self.query_one("#secrets-panel").border_title = f"Secrets — {self._model_name}"
        dt = self.query_one("#secrets-table", DataTable)
        dt.add_columns("ID", "Owner", "Rev", "Rotation", "Label")
        dt.display = False
        self._fetch(self._controller_name, self._model_name)

    @work
    async def _fetch(self, controller_name: str, model_name: str) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                secrets, content_map = await client.get_secrets_with_content(model_name)
            self._secret_contents = content_map
            self._populate(secrets)
        except (JujuError, OSError, asyncio.TimeoutError, KeyError) as exc:
            logger.exception("Failed to fetch secrets for model '%s'", model_name)
            self._show_error(str(exc))

    def _populate(self, secrets: list[SecretInfo]) -> None:
        self._secrets = secrets
        loading = self.query_one("#secrets-loading", Static)
        loading.display = False
        dt = self.query_one("#secrets-table", DataTable)
        if not secrets:
            loading.update("No secrets found.")
            loading.display = True
            return
        for i, s in enumerate(secrets):
            secret_id = s.uri.split(":", 1)[-1] if ":" in s.uri else s.uri
            dt.add_row(
                Text(secret_id, style=palette.LINK),
                s.owner or "—",
                str(s.revision),
                s.rotate_policy or "never",
                s.label or "—",
                key=str(i),
            )
        dt.display = True

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(str(event.row_key.value))
        if 0 <= idx < len(self._secrets):
            secret = self._secrets[idx]
            prefetched = self._secret_contents.get(secret.uri)
            self.app.push_screen(
                SecretDetailScreen(
                    self._controller_name,
                    self._model_name,
                    secret,
                    prefetched_content=prefetched,
                )
            )

    def _show_error(self, error: str) -> None:
        loading = self.query_one("#secrets-loading", Static)
        loading.update(Text(f"Error: {error}", style="bold red"))
        loading.display = True

    def action_refresh(self) -> None:
        """Re-fetch secrets and content, discarding the current data."""
        self._secrets = []
        self._secret_contents = {}
        dt = self.query_one("#secrets-table", DataTable)
        dt.clear()
        dt.display = False
        loading = self.query_one("#secrets-loading", Static)
        loading.update("Loading…")
        loading.display = True
        self.notify("Refreshing secrets…", timeout=2)
        self._fetch(self._controller_name, self._model_name)
