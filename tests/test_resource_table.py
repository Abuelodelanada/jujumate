from unittest.mock import patch

import pytest
import pytest_asyncio
from textual.widgets import DataTable, Label

from jujumate.widgets.resource_table import Column, ResourceTable


@pytest.fixture
def columns():
    return [Column("Name", "name"), Column("Status", "status", width=10)]


@pytest_asyncio.fixture
async def mounted_table(pilot, columns):
    """A ResourceTable mounted on the shared pilot screen, ready for testing."""
    table = ResourceTable(columns=columns, id="test-table")
    await pilot.app.screen.mount(table)
    await pilot.pause()
    return table


@pytest.mark.asyncio
async def test_resource_table_renders_columns(mounted_table):
    # GIVEN a mounted ResourceTable with two columns
    # WHEN we inspect the underlying DataTable
    dt = mounted_table.query_one(DataTable)
    # THEN it has exactly two columns
    assert len(dt.columns) == 2


@pytest.mark.asyncio
async def test_update_rows_populates_table(mounted_table):
    # GIVEN a mounted ResourceTable
    # WHEN update_rows is called with two rows
    mounted_table.update_rows([("aws", "active"), ("lxd", "active")])
    # THEN the DataTable has two rows
    assert mounted_table.query_one(DataTable).row_count == 2


@pytest.mark.asyncio
async def test_update_rows_shows_empty_label_when_no_data(mounted_table):
    # GIVEN a mounted ResourceTable
    # WHEN update_rows is called with an empty list
    mounted_table.update_rows([])
    # THEN the empty-label is visible
    label = mounted_table.query_one("#empty-label", Label)
    assert label.display is True


@pytest.mark.asyncio
async def test_update_rows_hides_empty_label_when_has_data(mounted_table):
    # GIVEN a mounted ResourceTable
    # WHEN update_rows is called with one row
    mounted_table.update_rows([("aws", "active")])
    # THEN the empty-label is hidden
    label = mounted_table.query_one("#empty-label", Label)
    assert label.display is False


@pytest.mark.asyncio
async def test_set_loading(mounted_table):
    # GIVEN a mounted ResourceTable
    # WHEN set_loading(True) is called
    mounted_table.set_loading(True)
    # THEN _is_loading is True
    assert mounted_table._is_loading is True

    # WHEN set_loading(False) is called
    mounted_table.set_loading(False)
    # THEN _is_loading is False
    assert mounted_table._is_loading is False


@pytest.mark.asyncio
async def test_resource_table_reset_columns(mounted_table, pilot):
    # GIVEN a mounted ResourceTable with data in it
    mounted_table.update_rows([("aws", "active")])

    # WHEN reset_columns is called with a new single-column set
    new_columns = [Column("Region", "region")]
    mounted_table.reset_columns(new_columns)
    await pilot.pause()

    # THEN the DataTable now has exactly one column and zero rows
    dt = mounted_table.query_one(DataTable)
    assert len(dt.columns) == 1
    assert dt.row_count == 0


@pytest.mark.asyncio
async def test_resource_table_table_focused_message_posted(mounted_table, pilot):
    # GIVEN a mounted ResourceTable
    posted: list = []
    with patch.object(mounted_table, "post_message", side_effect=posted.append):
        # WHEN the internal DataTable receives focus
        pilot.app.screen.set_focus(mounted_table.query_one(DataTable))
        await pilot.pause()

    # THEN a TableFocused message is posted
    assert any(isinstance(m, ResourceTable.TableFocused) for m in posted)
