import pytest
from textual.widgets import DataTable, Label

from jujumate.app import JujuMateApp
from jujumate.widgets.resource_table import Column, ResourceTable


@pytest.fixture
def columns():
    return [Column("Name", "name"), Column("Status", "status", width=10)]


@pytest.mark.asyncio
async def test_resource_table_renders_columns(columns):
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()
        dt = table.query_one(DataTable)
        assert len(dt.columns) == 2


@pytest.mark.asyncio
async def test_update_rows_populates_table(columns):
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()
        table.update_rows([("aws", "active"), ("lxd", "active")])
        assert table.query_one(DataTable).row_count == 2


@pytest.mark.asyncio
async def test_update_rows_shows_empty_label_when_no_data(columns):
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()
        table.update_rows([])
        label = table.query_one("#empty-label", Label)
        assert label.display is True


@pytest.mark.asyncio
async def test_update_rows_hides_empty_label_when_has_data(columns):
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()
        table.update_rows([("aws", "active")])
        label = table.query_one("#empty-label", Label)
        assert label.display is False


@pytest.mark.asyncio
async def test_set_loading(columns):
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()
        table.set_loading(True)
        assert table._is_loading is True
        table.set_loading(False)
        assert table._is_loading is False
