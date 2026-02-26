import pytest

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
