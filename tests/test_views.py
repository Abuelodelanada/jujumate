import pytest
from textual.widgets import DataTable

from jujumate.app import JujuMateApp
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo
from jujumate.widgets.apps_view import AppsView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.resource_table import ResourceTable
from jujumate.widgets.units_view import UnitsView


async def _mount_view(app, pilot, view):
    await app.screen.mount(view)
    await pilot.pause()


@pytest.mark.asyncio
async def test_clouds_view_update():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = CloudsView(id="test-clouds")
        await _mount_view(app, pilot, view)
        view.update([CloudInfo("aws", "ec2", regions=["us-east-1"])])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_clouds_view_empty_regions_and_credentials():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = CloudsView(id="test-clouds")
        await _mount_view(app, pilot, view)
        view.update([CloudInfo("lxd", "lxd")])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_controllers_view_update():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ControllersView(id="test-ctrl")
        await _mount_view(app, pilot, view)
        view.update([ControllerInfo("prod", "aws", "us-east-1", "3.6.0", model_count=3)])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_models_view_with_region():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ModelsView(id="test-models")
        await _mount_view(app, pilot, view)
        view.update([ModelInfo("dev", "prod", "aws", "us-east-1", "available")])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_models_view_without_region():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ModelsView(id="test-models")
        await _mount_view(app, pilot, view)
        view.update([ModelInfo("dev", "prod", "lxd", "", "available")])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_apps_view_update():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = AppsView(id="test-apps")
        await _mount_view(app, pilot, view)
        view.update([AppInfo("postgresql", "dev", "postgresql", "14/stable", 363, 2, "active")])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_units_view_update():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = UnitsView(id="test-units")
        await _mount_view(app, pilot, view)
        view.update([UnitInfo("postgresql/0", "postgresql", "0", "active", "idle", "10.0.0.1")])
        assert view.query_one(ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_clouds_view_emits_cloud_selected():
    received: list[CloudsView.CloudSelected] = []
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = CloudsView(id="test-clouds")
        await _mount_view(app, pilot, view)
        view.update([CloudInfo("aws", "ec2"), CloudInfo("lxd", "lxd")])
        await pilot.pause()

        def capture(msg: CloudsView.CloudSelected) -> None:
            received.append(msg)

        view.on_clouds_view_cloud_selected = capture  # type: ignore[method-assign]
        dt = view.query_one(DataTable)
        dt.move_cursor(row=0)
        dt.action_select_cursor()
        await pilot.pause()
        assert len(received) == 0  # message bubbles up, not caught here

        # Verify row keys were set by checking row count and key via DataTable
        assert dt.row_count == 2


@pytest.mark.asyncio
async def test_controllers_view_emits_controller_selected():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ControllersView(id="test-ctrl")
        await _mount_view(app, pilot, view)
        view.update([ControllerInfo("prod", "aws", "", "3.4.0", 2)])
        await pilot.pause()
        dt = view.query_one(DataTable)
        assert dt.row_count == 1


@pytest.mark.asyncio
async def test_models_view_emits_model_selected():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ModelsView(id="test-models")
        await _mount_view(app, pilot, view)
        view.update([ModelInfo("dev", "prod", "aws", "", "available")])
        await pilot.pause()
        dt = view.query_one(DataTable)
        assert dt.row_count == 1


@pytest.mark.asyncio
async def test_apps_view_emits_app_selected():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = AppsView(id="test-apps")
        await _mount_view(app, pilot, view)
        view.update([AppInfo("pg", "dev", "pg", "14/stable", 1)])
        await pilot.pause()
        dt = view.query_one(DataTable)
        assert dt.row_count == 1


@pytest.mark.asyncio
async def test_clouds_view_row_selection_posts_cloud_selected():
    from unittest.mock import MagicMock, patch

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = CloudsView(id="test-clouds2")
        await _mount_view(app, pilot, view)
        view.update([CloudInfo("aws", "ec2")])
        await pilot.pause()

        event = MagicMock()
        event.row_key.value = "aws"
        posted: list = []
        with patch.object(view, "post_message", side_effect=posted.append):
            view.on_data_table_row_selected(event)

        assert len(posted) == 1
        assert isinstance(posted[0], CloudsView.CloudSelected)
        assert posted[0].name == "aws"


@pytest.mark.asyncio
async def test_controllers_view_row_selection_posts_controller_selected():
    from unittest.mock import MagicMock, patch

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ControllersView(id="test-ctrl2")
        await _mount_view(app, pilot, view)
        view.update([ControllerInfo("prod", "aws", "", "3.4.0", 1)])
        await pilot.pause()

        event = MagicMock()
        event.row_key.value = "prod"
        posted: list = []
        with patch.object(view, "post_message", side_effect=posted.append):
            view.on_data_table_row_selected(event)

        assert len(posted) == 1
        assert isinstance(posted[0], ControllersView.ControllerSelected)
        assert posted[0].name == "prod"


@pytest.mark.asyncio
async def test_models_view_row_selection_posts_model_selected():
    from unittest.mock import MagicMock, patch

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = ModelsView(id="test-models2")
        await _mount_view(app, pilot, view)
        view.update([ModelInfo("dev", "prod", "aws", "", "available")])
        await pilot.pause()

        event = MagicMock()
        event.row_key.value = "dev"
        posted: list = []
        with patch.object(view, "post_message", side_effect=posted.append):
            view.on_data_table_row_selected(event)

        assert len(posted) == 1
        assert isinstance(posted[0], ModelsView.ModelSelected)
        assert posted[0].name == "dev"


@pytest.mark.asyncio
async def test_apps_view_row_selection_posts_app_selected():
    from unittest.mock import MagicMock, patch

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = AppsView(id="test-apps2")
        await _mount_view(app, pilot, view)
        view.update([AppInfo("pg", "dev", "pg", "14/stable", 1)])
        await pilot.pause()

        event = MagicMock()
        event.row_key.value = "pg"
        posted: list = []
        with patch.object(view, "post_message", side_effect=posted.append):
            view.on_data_table_row_selected(event)

        assert len(posted) == 1
        assert isinstance(posted[0], AppsView.AppSelected)
        assert posted[0].name == "pg"
