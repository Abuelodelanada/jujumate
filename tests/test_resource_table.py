from unittest.mock import patch

import pytest
from textual.widgets import DataTable, Label

from jujumate.app import JujuMateApp
from jujumate.widgets.resource_table import Column, ResourceTable


@pytest.fixture
def columns():
    return [Column("Name", "name"), Column("Status", "status", width=10)]


@pytest.mark.asyncio
async def test_resource_table_renders_columns(columns):
    # GIVEN a ResourceTable with two columns
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()

        # WHEN we inspect the underlying DataTable
        dt = table.query_one(DataTable)

        # THEN it has exactly two columns
        assert len(dt.columns) == 2


@pytest.mark.asyncio
async def test_update_rows_populates_table(columns):
    # GIVEN a mounted ResourceTable
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()

        # WHEN update_rows is called with two rows
        table.update_rows([("aws", "active"), ("lxd", "active")])

        # THEN the DataTable has two rows
        assert table.query_one(DataTable).row_count == 2


@pytest.mark.asyncio
async def test_update_rows_shows_empty_label_when_no_data(columns):
    # GIVEN a mounted ResourceTable
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()

        # WHEN update_rows is called with an empty list
        table.update_rows([])

        # THEN the empty-label is visible
        label = table.query_one("#empty-label", Label)
        assert label.display is True


@pytest.mark.asyncio
async def test_update_rows_hides_empty_label_when_has_data(columns):
    # GIVEN a mounted ResourceTable
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()

        # WHEN update_rows is called with one row
        table.update_rows([("aws", "active")])

        # THEN the empty-label is hidden
        label = table.query_one("#empty-label", Label)
        assert label.display is False


@pytest.mark.asyncio
async def test_set_loading(columns):
    # GIVEN a mounted ResourceTable
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-table")
        await app.screen.mount(table)
        await pilot.pause()

        # WHEN set_loading(True) is called
        table.set_loading(True)
        # THEN _is_loading is True
        assert table._is_loading is True

        # WHEN set_loading(False) is called
        table.set_loading(False)
        # THEN _is_loading is False
        assert table._is_loading is False


@pytest.mark.asyncio
async def test_resource_table_reset_columns(columns):
    # GIVEN a mounted ResourceTable with two original columns
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-reset")
        await app.screen.mount(table)
        await pilot.pause()
        table.update_rows([("aws", "active")])

        # WHEN reset_columns is called with a new single-column set
        new_columns = [Column("Region", "region")]
        table.reset_columns(new_columns)
        await pilot.pause()

        # THEN the DataTable now has exactly one column and zero rows
        dt = table.query_one(DataTable)
        assert len(dt.columns) == 1
        assert dt.row_count == 0


@pytest.mark.asyncio
async def test_resource_table_table_focused_message_posted(columns):
    # GIVEN a mounted ResourceTable
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = ResourceTable(columns=columns, id="test-focused")
        await app.screen.mount(table)
        await pilot.pause()

        posted: list = []
        with patch.object(table, "post_message", side_effect=posted.append):
            # WHEN the internal DataTable receives focus
            pilot.app.screen.set_focus(table.query_one(DataTable))
            await pilot.pause()

        # THEN a TableFocused message is posted
        assert any(isinstance(m, ResourceTable.TableFocused) for m in posted)
