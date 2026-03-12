import asyncio
import logging
from pathlib import Path

from juju.errors import JujuError
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen

from jujumate.client.juju_client import JujuClient
from jujumate.models.entities import RelationInfo
from jujumate.widgets.relation_data_view import RelationDataView

logger = logging.getLogger(__name__)


class RelationDataScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", show=False)]
    DEFAULT_CSS = (Path(__file__).parent / "relation_data_screen.tcss").read_text()

    def __init__(self, controller_name: str, model_name: str, relation: RelationInfo) -> None:
        super().__init__()
        self._controller_name = controller_name
        self._model_name = model_name
        self._relation = relation

    def compose(self) -> ComposeResult:
        yield RelationDataView(id="relation-data-view")

    def on_mount(self) -> None:
        view = self.query_one(RelationDataView)
        provider = self._relation.provider.split(":")[0]
        requirer = self._relation.requirer.split(":")[0]
        view.border_title = f"Relation #{self._relation.relation_id} — {provider} ↔ {requirer}"
        view.show_loading(self._relation)
        self._fetch(self._controller_name, self._model_name, self._relation, provider, requirer)

    @work
    async def _fetch(
        self,
        controller_name: str,
        model_name: str,
        relation: RelationInfo,
        provider_app: str,
        requirer_app: str,
    ) -> None:
        try:
            async with JujuClient(controller_name=controller_name) as client:
                entries = await client.get_relation_data(
                    model_name, relation.relation_id, provider_app, requirer_app
                )
            self.query_one(RelationDataView).update(relation, entries)
        except (JujuError, OSError, asyncio.TimeoutError, KeyError) as exc:
            logger.exception("Failed to fetch relation data for relation %d", relation.relation_id)
            self.query_one(RelationDataView).show_error(relation, str(exc))
