"""Single-tab navigator combining cloud, controller and model selection with detail strip."""

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from jujumate import palette
from jujumate.models.entities import CloudInfo, ControllerInfo, ModelInfo
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.models_view import ModelsView


def _detail_row(label: str, value: str, width: int = 14) -> str:
    return f"  [bold]{label.ljust(width)}[/]{value}"


class NavigatorView(Widget):
    """Three-panel navigator: detail strip at top, selection tables at bottom.

    Selecting a cloud filters the controllers list; selecting a controller
    filters the models list; selecting a model posts ModelSelected.

    The top strip shows key fields of the currently selected cloud,
    controller and model respectively.
    """

    DEFAULT_CSS = (Path(__file__).parent / "navigator_view.tcss").read_text()

    # ── messages ────────────────────────────────────────────────────────────

    class CloudSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class ControllerSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class ModelSelected(Message):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    # ── state ────────────────────────────────────────────────────────────────

    _selected_cloud: reactive[str | None] = reactive(None)
    _selected_controller: reactive[str | None] = reactive(None)
    _selected_model: reactive[str | None] = reactive(None)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._all_clouds: list[CloudInfo] = []
        self._all_controllers: list[ControllerInfo] = []
        self._all_models: list[ModelInfo] = []

    # ── compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical

        with Vertical(id="nav-container"):
            with Horizontal(id="nav-detail-strip"):
                yield Static("", id="nav-cloud-detail")
                yield Static("", id="nav-controller-detail")
                yield Static("", id="nav-model-detail")
            with Horizontal(id="nav-selector-strip"):
                yield CloudsView(id="clouds-view")
                yield ControllersView(id="controllers-view")
                yield ModelsView(id="models-view")

    def on_mount(self) -> None:
        self._refresh_cloud_detail()
        self._refresh_controller_detail()
        self._refresh_model_detail()

    # ── public update API ────────────────────────────────────────────────────

    def update_clouds(self, clouds: list[CloudInfo]) -> None:
        self._all_clouds = clouds
        self.query_one("#clouds-view", CloudsView).update(clouds)

    def update_controllers(self, controllers: list[ControllerInfo]) -> None:
        self._all_controllers = controllers
        self._refresh_controllers_view()

    def update_models(self, models: list[ModelInfo]) -> None:
        self._all_models = models
        self._refresh_models_view()

    def select_model(self, controller: str, model: str) -> None:
        self.query_one("#models-view", ModelsView).select_model(controller, model)

    def reset_selection(self) -> None:
        self._selected_cloud = None
        self._selected_controller = None
        self._selected_model = None
        self._refresh_controllers_view()
        self._refresh_models_view()
        self._refresh_cloud_detail()
        self._refresh_controller_detail()
        self._refresh_model_detail()

    # ── internal refresh helpers ─────────────────────────────────────────────

    def _refresh_controllers_view(self) -> None:
        filtered = [
            c
            for c in self._all_controllers
            if self._selected_cloud is None or c.cloud == self._selected_cloud
        ]
        self.query_one("#controllers-view", ControllersView).update(filtered)

    def _refresh_models_view(self) -> None:
        if self._selected_controller is not None:
            filtered = [m for m in self._all_models if m.controller == self._selected_controller]
        elif self._selected_cloud is not None:
            cloud_controllers = {
                c.name for c in self._all_controllers if c.cloud == self._selected_cloud
            }
            filtered = [m for m in self._all_models if m.controller in cloud_controllers]
        else:
            filtered = list(self._all_models)
        self.query_one("#models-view", ModelsView).update(filtered)

    def _refresh_cloud_detail(self) -> None:
        panel = self.query_one("#nav-cloud-detail", Static)
        cloud = next((c for c in self._all_clouds if c.name == self._selected_cloud), None)
        if cloud is None:
            panel.update(self._placeholder("Cloud"))
            panel.border_title = f"[{palette.MUTED}]Cloud[/]"
            return
        regions = ", ".join(cloud.regions[:3]) if cloud.regions else "—"
        if len(cloud.regions) > 3:
            regions += f" +{len(cloud.regions) - 3}"
        creds = str(len(cloud.credentials)) if cloud.credentials else "0"
        lines = [
            f"  [{palette.ACCENT}]{cloud.name}[/]",
            _detail_row("Type", cloud.type),
            _detail_row("Regions", f"{len(cloud.regions)}  [{palette.MUTED}]{regions}[/]"),
            _detail_row("Credentials", creds),
        ]
        panel.update("\n".join(lines))
        panel.border_title = f"[{palette.SUCCESS}]Cloud[/]"

    def _refresh_controller_detail(self) -> None:
        panel = self.query_one("#nav-controller-detail", Static)
        ctrl = next((c for c in self._all_controllers if c.name == self._selected_controller), None)
        if ctrl is None:
            panel.update(self._placeholder("Controller"))
            panel.border_title = f"[{palette.MUTED}]Controller[/]"
            return
        lines = [
            f"  [{palette.ACCENT}]{ctrl.name}[/]",
            _detail_row("Cloud", ctrl.cloud),
            _detail_row("Region", ctrl.region or "—"),
            _detail_row("Juju", ctrl.juju_version or "—"),
            _detail_row("Models", str(ctrl.model_count)),
        ]
        panel.update("\n".join(lines))
        panel.border_title = f"[{palette.SUCCESS}]Controller[/]"

    def _refresh_model_detail(self) -> None:
        panel = self.query_one("#nav-model-detail", Static)
        model = next(
            (
                m
                for m in self._all_models
                if self._selected_model
                and m.name == self._selected_model
                and (not self._selected_controller or m.controller == self._selected_controller)
            ),
            None,
        )
        if model is None:
            panel.update(self._placeholder("Model"))
            panel.border_title = f"[{palette.MUTED}]Model[/]"
            return
        status_color = palette.status_color(model.status) or palette.MUTED
        lines = [
            f"  [{palette.ACCENT}]{model.name}[/]",
            _detail_row("Status", f"[{status_color}]{model.status}[/]"),
            _detail_row("Controller", model.controller),
            _detail_row("Machines", str(model.machine_count)),
            _detail_row("Apps", str(model.app_count)),
        ]
        panel.update("\n".join(lines))
        panel.border_title = f"[{palette.SUCCESS}]Model[/]"

    @staticmethod
    def _placeholder(label: str) -> str:
        return f"  [{palette.MUTED}]— select a {label.lower()} —[/]"

    # ── event handlers ───────────────────────────────────────────────────────

    def on_clouds_view_cloud_selected(self, message: CloudsView.CloudSelected) -> None:
        message.stop()
        self._selected_cloud = message.name
        self._selected_controller = None
        self._selected_model = None
        self._refresh_controllers_view()
        self._refresh_models_view()
        self._refresh_cloud_detail()
        self._refresh_controller_detail()
        self._refresh_model_detail()
        self.post_message(NavigatorView.CloudSelected(message.name))
        self.call_after_refresh(self.query_one("#controllers-table").focus)

    def on_controllers_view_controller_selected(
        self, message: ControllersView.ControllerSelected
    ) -> None:
        message.stop()
        self._selected_controller = message.name
        self._selected_model = None
        self._refresh_models_view()
        self._refresh_controller_detail()
        self._refresh_model_detail()
        self.post_message(NavigatorView.ControllerSelected(message.name))
        self.call_after_refresh(self.query_one("#models-table").focus)

    def on_models_view_model_selected(self, message: ModelsView.ModelSelected) -> None:
        message.stop()
        parts = message.name.split("/", 1)
        if len(parts) == 2:
            self._selected_controller = parts[0]
            self._selected_model = parts[1]
        else:
            self._selected_model = message.name
        self._refresh_model_detail()
        self.post_message(NavigatorView.ModelSelected(message.name))
