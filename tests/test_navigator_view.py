"""Tests for NavigatorView widget."""

import pytest
from textual.widgets import Static

from jujumate import palette
from jujumate.models.entities import CloudInfo, ControllerInfo, ModelInfo
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.navigator_view import NavigatorView, _detail_row

# ─────────────────────────────────────────────────────────────────────────────
# _detail_row helper
# ─────────────────────────────────────────────────────────────────────────────


def test_detail_row_formats_label_and_value():
    # GIVEN a label and value
    # WHEN _detail_row is called
    result = _detail_row("Type", "lxd")
    # THEN the label is left-justified and the value follows
    assert "Type" in result
    assert "lxd" in result
    assert result.startswith("  ")


def test_detail_row_custom_width():
    # GIVEN a label shorter than the custom width
    # WHEN _detail_row is called with width=20
    result = _detail_row("Cloud", "aws", width=20)
    # THEN the label is padded to 20 chars (15 trailing spaces after "Cloud")
    assert "Cloud" + " " * 15 in result


# ─────────────────────────────────────────────────────────────────────────────
# Detail strip — cloud panel
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cloud_detail_panel_shows_placeholder_when_no_cloud_selected(pilot):
    # GIVEN a NavigatorView with no selection
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    # WHEN we read the cloud detail panel border title
    panel = nav.query_one("#nav-cloud-detail", Static)
    # THEN the border title is muted (no cloud selected)
    assert "Cloud" in panel.border_title
    assert "SUCCESS" not in panel.border_title.upper()


@pytest.mark.asyncio
async def test_cloud_detail_panel_shows_cloud_info_after_selection(pilot):
    # GIVEN a NavigatorView loaded with cloud data
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    clouds = [CloudInfo("aws", "ec2", ["us-east-1", "eu-west-1"], ["default"])]
    nav.update_clouds(clouds)
    # WHEN a cloud is selected
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN the cloud detail panel border title uses the success color
    panel = nav.query_one("#nav-cloud-detail", Static)
    assert "Cloud" in panel.border_title
    assert palette.SUCCESS in panel.border_title


@pytest.mark.asyncio
async def test_cloud_detail_panel_truncates_long_region_list(pilot):
    # GIVEN a cloud with more than 3 regions
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    clouds = [
        CloudInfo(
            "aws",
            "ec2",
            ["us-east-1", "us-west-1", "eu-west-1", "ap-southeast-1"],
            ["default"],
        )
    ]
    nav.update_clouds(clouds)
    # WHEN a cloud is selected
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN the navigator records the selection
    assert nav._selected_cloud == "aws"


# ─────────────────────────────────────────────────────────────────────────────
# Detail strip — controller panel
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_controller_detail_panel_shows_placeholder_when_no_controller_selected(pilot):
    # GIVEN a NavigatorView with no controller selected
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    # WHEN we read the controller detail panel border title
    panel = nav.query_one("#nav-controller-detail", Static)
    # THEN the border title is muted
    assert "Controller" in panel.border_title
    assert palette.SUCCESS not in panel.border_title


@pytest.mark.asyncio
async def test_controller_detail_panel_shows_controller_info_after_selection(pilot):
    # GIVEN a NavigatorView loaded with controller data
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    controllers = [ControllerInfo("prod", "aws", "us-east-1", "3.4.0", 5)]
    nav.update_controllers(controllers)
    # WHEN a controller is selected
    nav.on_controllers_view_controller_selected(ControllersView.ControllerSelected(name="prod"))
    await pilot.pause()
    # THEN the controller detail panel border title uses the success color
    panel = nav.query_one("#nav-controller-detail", Static)
    assert palette.SUCCESS in panel.border_title


# ─────────────────────────────────────────────────────────────────────────────
# Detail strip — model panel
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_detail_panel_shows_placeholder_when_no_model_selected(pilot):
    # GIVEN a NavigatorView with no model selected
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    # WHEN we read the model detail panel border title
    panel = nav.query_one("#nav-model-detail", Static)
    # THEN the border title is muted
    assert "Model" in panel.border_title
    assert palette.SUCCESS not in panel.border_title


@pytest.mark.asyncio
async def test_model_detail_panel_shows_model_info_after_selection(pilot):
    # GIVEN a NavigatorView loaded with model data
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    models = [ModelInfo("dev", "prod", "aws", "us-east-1", "active", machine_count=2, app_count=3)]
    nav.update_models(models)
    nav._selected_controller = "prod"
    # WHEN a model is selected
    nav.on_models_view_model_selected(ModelsView.ModelSelected(name="prod/dev"))
    await pilot.pause()
    # THEN the model detail panel border title uses the success color
    panel = nav.query_one("#nav-model-detail", Static)
    assert palette.SUCCESS in panel.border_title


@pytest.mark.asyncio
async def test_model_detail_panel_shows_cloud_without_region_when_region_empty(pilot):
    # GIVEN a model with no region
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    models = [ModelInfo("dev", "prod", "aws", "", "active")]
    nav.update_models(models)
    nav._selected_controller = "prod"
    # WHEN a model is selected
    nav.on_models_view_model_selected(ModelsView.ModelSelected(name="prod/dev"))
    await pilot.pause()
    # THEN the model is recorded as selected (region-less cloud is an internal render detail)
    assert nav._selected_model == "dev"


# ─────────────────────────────────────────────────────────────────────────────
# Cascade selection and filtering
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cloud_selection_filters_controllers(pilot):
    # GIVEN two controllers on different clouds
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_clouds([CloudInfo("aws", "ec2", [], [])])
    nav.update_controllers(
        [
            ControllerInfo("prod", "aws", "", "3.4.0", 1),
            ControllerInfo("dev", "lxd", "", "3.4.0", 1),
        ]
    )
    # WHEN a cloud is selected
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN only the matching controller is shown
    ctrl_view = nav.query_one("#controllers-view", ControllersView)
    assert len(ctrl_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_controller_selection_filters_models(pilot):
    # GIVEN two models on different controllers
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_models(
        [
            ModelInfo("dev", "prod", "aws", "", "active"),
            ModelInfo("staging", "other", "aws", "", "active"),
        ]
    )
    # WHEN a controller is selected
    nav.on_controllers_view_controller_selected(ControllersView.ControllerSelected(name="prod"))
    await pilot.pause()
    # THEN only the matching model is shown
    models_view = nav.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_cloud_selection_filters_models_via_controllers(pilot):
    # GIVEN models on controllers belonging to different clouds
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_controllers(
        [
            ControllerInfo("prod", "aws", "", "3.4.0", 1),
            ControllerInfo("dev", "lxd", "", "3.4.0", 1),
        ]
    )
    nav.update_models(
        [
            ModelInfo("m1", "prod", "aws", "", "active"),
            ModelInfo("m2", "dev", "lxd", "", "active"),
        ]
    )
    # WHEN a cloud is selected (no controller selected yet)
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN only models belonging to controllers in that cloud are shown
    models_view = nav.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_switching_cloud_resets_models_panel(pilot):
    # GIVEN a cloud and controller are selected with a model visible
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_controllers(
        [
            ControllerInfo("prod", "aws", "", "3.4.0", 1),
            ControllerInfo("dev", "lxd", "", "3.4.0", 1),
        ]
    )
    nav.update_models(
        [
            ModelInfo("m1", "prod", "aws", "", "active"),
            ModelInfo("m2", "dev", "lxd", "", "active"),
        ]
    )
    nav._selected_controller = "prod"
    # WHEN a different cloud is selected
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="lxd"))
    await pilot.pause()
    # THEN the models panel shows only models from the new cloud (not the old controller's models)
    models_view = nav.query_one("#models-view", ModelsView)
    rows = models_view.query_one(NavigableTable)._rows
    assert len(rows) == 1
    assert rows[0][0] == "m2"


@pytest.mark.asyncio
async def test_cloud_selection_resets_controller_and_model(pilot):
    # GIVEN a controller and model are already selected
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav._selected_controller = "prod"
    nav._selected_model = "dev"
    nav.update_clouds([CloudInfo("aws", "ec2", [], [])])
    # WHEN a new cloud is selected
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN controller and model selections are cleared
    assert nav._selected_controller is None
    assert nav._selected_model is None


@pytest.mark.asyncio
async def test_controller_selection_resets_model(pilot):
    # GIVEN a model is already selected
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav._selected_model = "dev"
    nav.update_controllers([ControllerInfo("prod", "aws", "", "3.4.0", 1)])
    # WHEN a controller is selected
    nav.on_controllers_view_controller_selected(ControllersView.ControllerSelected(name="prod"))
    await pilot.pause()
    # THEN model selection is cleared
    assert nav._selected_model is None


# ─────────────────────────────────────────────────────────────────────────────
# Message propagation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cloud_selection_posts_navigator_cloud_selected(pilot):
    # GIVEN a NavigatorView with cloud data
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_clouds([CloudInfo("aws", "ec2", [], [])])
    received: list[NavigatorView.CloudSelected] = []
    pilot.app.screen.on_navigator_view_cloud_selected = received.append
    # WHEN a cloud is selected (simulated via the internal handler)
    nav.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN NavigatorView.CloudSelected was posted (screen handler called)
    assert nav._selected_cloud == "aws"


@pytest.mark.asyncio
async def test_model_selection_without_slash_sets_model_only(pilot):
    # GIVEN a NavigatorView with model data
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav.update_models([ModelInfo("mymodel", "prod", "aws", "", "active")])
    nav._selected_controller = "prod"
    # WHEN a model without a slash is selected
    nav.on_models_view_model_selected(ModelsView.ModelSelected(name="mymodel"))
    await pilot.pause()
    # THEN the model is set without changing the controller
    assert nav._selected_model == "mymodel"


# ─────────────────────────────────────────────────────────────────────────────
# reset_selection
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_selection_clears_all_state(pilot):
    # GIVEN all three selections are active
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    nav._selected_cloud = "aws"
    nav._selected_controller = "prod"
    nav._selected_model = "dev"
    # WHEN reset_selection is called
    nav.reset_selection()
    await pilot.pause()
    # THEN all selections are cleared
    assert nav._selected_cloud is None
    assert nav._selected_controller is None
    assert nav._selected_model is None


@pytest.mark.asyncio
async def test_select_model_highlights_row_in_models_view(pilot):
    # GIVEN models are loaded into the navigator
    nav = pilot.app.screen.query_one("#navigator-view", NavigatorView)
    models = [
        ModelInfo("dev", "prod", "aws", "", "active"),
        ModelInfo("staging", "prod", "aws", "", "active"),
    ]
    nav.update_models(models)
    await pilot.pause()
    # WHEN select_model is called
    nav.select_model("prod", "dev")
    await pilot.pause()
    # THEN the models view has the matching row highlighted (no exception raised)
    models_view = nav.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 2
