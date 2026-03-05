"""Modal screens for controller offers list and offer detail."""

import logging
from dataclasses import dataclass

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label, Rule, Static

from jujumate import palette
from jujumate.client.juju_client import JujuClient
from jujumate.config import load_config
from jujumate.models.entities import ControllerOfferInfo, SAASInfo
from jujumate.widgets.status_view import _colored_status

logger = logging.getLogger(__name__)


@dataclass
class _ConsumerEntry:
    controller: str
    saas: SAASInfo


_ACCESS_COLORS: dict[str, str] = {
    "admin": palette.SUCCESS,
    "consume": palette.LINK,
    "read": palette.MUTED,
}


def _colored_access(access: str) -> str:
    """Return Rich markup string for access level."""
    color = _ACCESS_COLORS.get(access.strip().lower(), "")
    return f"[{color}]{access}[/]" if color else access


def _normalize_url(url: str) -> str:
    """Strip optional 'controller:' prefix so URLs compare equal regardless of format."""
    return url.split(":", 1)[-1] if ":" in url else url


class OfferDetailScreen(ModalScreen):
    """Modal overlay showing full details of a single offer."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]

    DEFAULT_CSS = """
    OfferDetailScreen {
        align: center middle;
    }
    OfferDetailScreen #detail-panel {
        width: 88%;
        height: auto;
        max-height: 85%;
        background: $surface;
        border: round $accent;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }
    OfferDetailScreen #top-row {
        height: auto;
    }
    OfferDetailScreen #fields-col {
        width: 1fr;
        height: auto;
        border-right: tall $panel-lighten-2;
        padding-right: 2;
    }
    OfferDetailScreen #endpoints-col {
        width: 1fr;
        height: auto;
        padding-left: 2;
    }
    OfferDetailScreen .detail-row {
        height: auto;
    }
    OfferDetailScreen .section-label {
        height: auto;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    OfferDetailScreen .sub-table {
        height: auto;
        max-height: 8;
        margin-top: 0;
    }
    OfferDetailScreen Rule {
        margin-top: 1;
        color: $panel-lighten-2;
    }
    """

    def __init__(self, offer: ControllerOfferInfo, controller_name: str) -> None:
        super().__init__()
        self._offer = offer
        self._controller_name = controller_name

    def compose(self) -> ComposeResult:
        o = self._offer
        fields = [
            ("Model", o.model),
            ("Offer URL", o.offer_url),
            ("Application", o.application),
            ("Charm", o.charm),
            ("Description", o.description or "—"),
            ("Access", o.access or "—"),
        ]
        col_width = max(len(f) for f, _ in fields) + 2  # +2 for ": "
        with Vertical(id="detail-panel"):
            with Horizontal(id="top-row"):
                with Vertical(id="fields-col"):
                    for field, value in fields:
                        label = f"{field}:".ljust(col_width)
                        if field == "Offer URL":
                            styled = f"[{palette.LINK}]{value}[/]"
                        elif field == "Access":
                            styled = _colored_access(value)
                        else:
                            styled = value
                        yield Label(f"[bold]{label}[/bold]{styled}", classes="detail-row")
                with Vertical(id="endpoints-col"):
                    yield Label("Endpoints:", classes="section-label")
                    yield DataTable(id="endpoints-table", show_cursor=False, classes="sub-table")
            yield Rule()
            yield Label("Connected from:", classes="section-label")
            yield Label("Loading…", id="consumers-loading")
            yield DataTable(id="connections-table", show_cursor=False, classes="sub-table")

    def on_mount(self) -> None:
        o = self._offer
        active_info = (
            f"  ({o.active_connections}/{o.total_connections} active)"
            if o.total_connections
            else ""
        )
        self.query_one("#detail-panel").border_title = f"Offer — {o.name}{active_info}"
        ep_dt = self.query_one("#endpoints-table", DataTable)
        ep_dt.add_columns("Name", "Interface", "Role")
        for ep in self._offer.endpoints:
            ep_dt.add_row(ep.name, ep.interface, ep.role)
        if not self._offer.endpoints:
            ep_dt.add_row("—", "—", "—")

        conn_dt = self.query_one("#connections-table", DataTable)
        conn_dt.add_columns("Controller", "Model", "Application", "Status")
        conn_dt.display = False
        self._fetch_consumers(self._controller_name, self._offer)

    @work
    async def _fetch_consumers(self, controller_name: str, offer: ControllerOfferInfo) -> None:
        """Scan all models across all known controllers for SAAS entries that consume this offer."""
        consumers: list[_ConsumerEntry] = []
        target_url = _normalize_url(offer.offer_url)
        try:
            all_controllers = load_config().controllers
        except Exception:
            all_controllers = [controller_name]

        for ctrl_name in all_controllers:
            try:
                async with JujuClient(controller_name=ctrl_name) as client:
                    model_names = await client.list_model_names()
                    for model_name in model_names:
                        try:
                            saas_list = await client.get_saas(model_name)
                            for s in saas_list:
                                if _normalize_url(s.url) == target_url:
                                    consumers.append(_ConsumerEntry(controller=ctrl_name, saas=s))
                        except Exception as exc:
                            logger.debug(
                                "Could not fetch SAAS for model '%s' on '%s': %s",
                                model_name,
                                ctrl_name,
                                exc,
                            )
            except Exception as exc:
                logger.debug("Could not connect to controller '%s': %s", ctrl_name, exc)

        self._populate_consumers(consumers)

    def _populate_consumers(self, consumers: list[_ConsumerEntry]) -> None:
        loading = self.query_one("#consumers-loading", Static)
        loading.display = False
        conn_dt = self.query_one("#connections-table", DataTable)
        if consumers:
            for entry in consumers:
                s = entry.saas
                app_name = Text.from_markup(f"[{palette.LINK}]{s.name}[/]")
                ctrl_name = Text.from_markup(f"[{palette.MUTED}]{entry.controller}[/]")
                conn_dt.add_row(ctrl_name, s.model, app_name, _colored_status(s.status))
            conn_dt.display = True
        else:
            loading.update("No known consumers.")
            loading.display = True


class OffersScreen(ModalScreen):
    """Modal overlay displaying all offers across the controller."""

    BINDINGS = [Binding("escape", "dismiss", show=False)]

    DEFAULT_CSS = """
    OffersScreen {
        align: center middle;
    }
    OffersScreen #offers-panel {
        width: 88%;
        height: 85%;
        background: $surface;
        border: round $accent;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }
    OffersScreen #offers-loading {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    OffersScreen DataTable {
        height: 1fr;
    }
    """

    def __init__(self, controller_name: str) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._offers: list[ControllerOfferInfo] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="offers-panel"):
            yield Label("Loading…", id="offers-loading")
            yield DataTable(id="offers-table", show_cursor=True, cursor_type="row")

    def on_mount(self) -> None:
        self.query_one("#offers-panel").border_title = f"Offers — {self._controller_name}"
        dt = self.query_one("#offers-table", DataTable)
        dt.add_columns("URL", "Access", "Endpoints", "Connected")
        dt.display = False
        self._fetch(self._controller_name)

    @work
    async def _fetch(self, controller_name: str) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                offers = await client.get_controller_offers()
            self._populate(offers)
        except Exception as exc:
            logger.exception("Failed to fetch offers for controller '%s'", controller_name)
            self._show_error(str(exc))

    def _populate(self, offers: list[ControllerOfferInfo]) -> None:
        self._offers = offers
        loading = self.query_one("#offers-loading", Static)
        loading.display = False
        dt = self.query_one("#offers-table", DataTable)
        if not offers:
            loading.update("No offers found.")
            loading.display = True
            return
        for i, o in enumerate(offers):
            ep_summary = ", ".join(ep.name for ep in o.endpoints) or "—"
            cnt = f"{o.active_connections}/{o.total_connections}"
            if o.total_connections == 0:
                connected = Text(cnt, style=palette.MUTED)
            elif o.active_connections == o.total_connections:
                connected = Text(cnt, style=palette.SUCCESS)
            else:
                connected = Text(cnt, style=palette.WARNING)
            dt.add_row(
                Text(o.offer_url, style=palette.LINK),
                Text.from_markup(_colored_access(o.access or "—")),
                ep_summary,
                connected,
                key=str(i),
            )
        dt.display = True

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(str(event.row_key.value))
        if 0 <= idx < len(self._offers):
            self.app.push_screen(OfferDetailScreen(self._offers[idx], self._controller_name))

    def _show_error(self, error: str) -> None:
        loading = self.query_one("#offers-loading", Static)
        loading.update(Text(f"Error: {error}", style="bold red"))
        loading.display = True
