from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.css.query import NoMatches
from textual.widgets import DataTable, Input, Label, TabbedContent
from textual.widgets._data_table import RowKey

from jujumate.app import JujuMateApp
from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    MachineInfo,
    ModelInfo,
    OfferInfo,
    RelationDataEntry,
    RelationInfo,
    SAASInfo,
    StorageInfo,
    UnitInfo,
)
from jujumate.widgets.app_config_view import (
    AppConfigView,
    _build_config_renderable,
)
from jujumate.widgets.app_config_view import (
    _format_plain_text as _ac_format_plain_text,
)
from jujumate.widgets.apps_view import AppsView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.relation_data_view import (
    RelationDataView,
    _build_relation_renderable,
    _kv_table,
    _unit_panel,
)
from jujumate.widgets.relation_data_view import (
    _format_plain_text as _rd_format_plain_text,
)
from jujumate.widgets.resource_table import Column, ResourceTable
from jujumate.widgets.status_view import (
    _MSG_TRUNC_WIDTH,
    StatusView,
    _colored_relation,
    _format_size_mib,
    _group_units,
    _group_units_by_machine,
    _TrackedScroll,
    _trunc_msg,
    _unit_name_text,
)
from jujumate.widgets.units_view import UnitsView


async def _mount_view(pilot, view):
    await pilot.app.screen.mount(view)
    await pilot.pause()


@contextmanager
def _capture_posted(obj):
    """Capture messages posted via obj.post_message within the context."""
    messages: list = []
    with patch.object(obj, "post_message", side_effect=messages.append):
        yield messages


def _mock_clipboard(view) -> None:
    """Replace copy_to_clipboard and notify on a view with MagicMocks."""
    view.app.copy_to_clipboard = MagicMock()
    view.notify = MagicMock()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id,view_class,entities,expected_rows",
    [
        pytest.param(
            "test-clouds-a",
            CloudsView,
            [CloudInfo("aws", "ec2", regions=["us-east-1"])],
            1,
            id="clouds",
        ),
        pytest.param(
            "test-ctrl-a",
            ControllersView,
            [ControllerInfo("prod", "aws", "us-east-1", "3.6.0", model_count=3)],
            1,
            id="controllers",
        ),
        pytest.param(
            "test-models-a",
            ModelsView,
            [ModelInfo("dev", "prod", "aws", "us-east-1", "available")],
            1,
            id="models-with-region",
        ),
    ],
)
async def test_view_update_row_count(pilot, view_id, view_class, entities, expected_rows):
    # GIVEN a freshly mounted view with no rows
    view = view_class(id=view_id)
    await _mount_view(pilot, view)

    # WHEN update is called with a single entity
    view.update(entities)

    # THEN the row count matches expected_rows
    assert len(view.query_one(NavigableTable)._rows) == expected_rows


@pytest.mark.asyncio
async def test_clouds_view_empty_regions(pilot):
    # GIVEN a mounted CloudsView
    view = CloudsView(id="test-clouds")
    await _mount_view(pilot, view)

    # WHEN a cloud with no regions is added
    view.update([CloudInfo("lxd", "lxd")])

    # THEN exactly one row is present
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_models_view_update_adds_row(pilot):
    # GIVEN a mounted ModelsView
    view = ModelsView(id="test-models")
    await _mount_view(pilot, view)

    # WHEN a model is added
    view.update([ModelInfo("dev", "prod", "lxd", "", "available")])

    # THEN exactly one row is present
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_clouds_view_emits_cloud_selected(pilot):
    # GIVEN a mounted CloudsView
    view = CloudsView(id="test-clouds")
    await _mount_view(pilot, view)

    # WHEN two clouds are added
    view.update([CloudInfo("aws", "ec2"), CloudInfo("lxd", "lxd")])
    await pilot.pause()
    nt = view.query_one(NavigableTable)

    # THEN both rows are present in the table
    assert len(nt._rows) == 2


@pytest.mark.asyncio
async def test_controllers_view_emits_controller_selected(pilot):
    # GIVEN a mounted ControllersView
    view = ControllersView(id="test-ctrl")
    await _mount_view(pilot, view)

    # WHEN a controller is added
    view.update([ControllerInfo("prod", "aws", "", "3.4.0", 2)])
    await pilot.pause()

    # THEN one row is present
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_models_view_emits_model_selected(pilot):
    # GIVEN a mounted ModelsView
    view = ModelsView(id="test-models")
    await _mount_view(pilot, view)

    # WHEN a model is added
    view.update([ModelInfo("dev", "prod", "aws", "", "available")])
    await pilot.pause()

    # THEN one row is present
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id,view_class,entities,msg_class,expected_name_attr,expected_name_value,row_key",
    [
        pytest.param(
            "test-clouds-b",
            CloudsView,
            [CloudInfo("aws", "ec2")],
            CloudsView.CloudSelected,
            "name",
            "aws",
            "aws",
            id="clouds",
        ),
        pytest.param(
            "test-ctrl-b",
            ControllersView,
            [ControllerInfo("prod", "aws", "", "3.4.0", 1)],
            ControllersView.ControllerSelected,
            "name",
            "prod",
            "prod",
            id="controllers",
        ),
        pytest.param(
            "test-models-b",
            ModelsView,
            [ModelInfo("dev", "prod", "aws", "", "available")],
            ModelsView.ModelSelected,
            "name",
            "prod/dev",
            "prod/dev",
            id="models",
        ),
    ],
)
async def test_view_row_selection_posts_message(
    pilot,
    view_id,
    view_class,
    entities,
    msg_class,
    expected_name_attr,
    expected_name_value,
    row_key,
):
    # GIVEN a mounted view populated with one entity
    view = view_class(id=view_id)
    await _mount_view(pilot, view)
    view.update(entities)
    await pilot.pause()

    # WHEN a row selection event is triggered
    with _capture_posted(view) as posted:
        view.on_navigable_table_row_selected(NavigableTable.RowSelected(key=row_key))

    # THEN a single message of the expected type is posted with the right name
    assert len(posted) == 1
    assert isinstance(posted[0], msg_class)
    assert getattr(posted[0], expected_name_attr) == expected_name_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id,update_method_name,entities,extra_kwargs,table_id",
    [
        pytest.param(
            "test-sv-apps",
            "update_apps",
            [AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")],
            {},
            "#status-apps-table",
            id="apps",
        ),
        pytest.param(
            "test-sv-units",
            "update_units",
            [UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1")],
            {"is_kubernetes": False},
            "#status-units-table",
            id="units",
        ),
        pytest.param(
            "test-sv-rels",
            "update_relations",
            [RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular")],
            {},
            "#status-rels-table",
            id="relations",
        ),
    ],
)
async def test_status_view_update_tables(
    pilot, view_id, update_method_name, entities, extra_kwargs, table_id
):
    # GIVEN a freshly mounted StatusView
    view = StatusView(id=view_id)
    await _mount_view(pilot, view)

    # WHEN the appropriate update method is called with one entity
    getattr(view, update_method_name)(entities, **extra_kwargs)
    await pilot.pause()

    # THEN the corresponding table has exactly one row
    assert view.query_one(table_id, ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_update_units_kubernetes(pilot):
    # GIVEN a mounted StatusView
    view = StatusView(id="test-status-units-k8s")
    await _mount_view(pilot, view)

    # WHEN units are updated with is_kubernetes=True
    view.update_units(
        [UnitInfo("pg/0", "pg", "", "active", "idle", address="10.1.2.3")], is_kubernetes=True
    )
    await pilot.pause()
    table = view.query_one("#status-units-table", ResourceTable).query_one("DataTable")

    # THEN the table has one row and uses the K8s column layout (no "Machine" column)
    assert table.row_count == 1
    col_labels = [str(col.label) for col in table.ordered_columns]
    assert "Machine" not in col_labels
    assert "Address" in col_labels


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_kubernetes",
    [
        pytest.param(True, id="k8s"),
        pytest.param(False, id="iaas"),
    ],
)
async def test_status_view_update_units_with_subordinate_prefix(pilot, is_kubernetes):
    # GIVEN a principal unit and a subordinate unit
    view = StatusView(id=f"test-sub-{'k8s' if is_kubernetes else 'iaas'}")
    await _mount_view(pilot, view)
    principal = UnitInfo("pg/0", "pg", "0", "active", "idle")
    subordinate = UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", subordinate_of="pg/0")

    # WHEN update_units is called with both units
    view.update_units([principal, subordinate], is_kubernetes=is_kubernetes)
    await pilot.pause()

    # THEN two rows are rendered in the units table
    table = view.query_one("#status-units-table", ResourceTable)
    assert table.query_one("DataTable").row_count == 2


def test_unit_name_text_leader_appends_star():
    # GIVEN a leader unit
    unit = UnitInfo("pg/0", "pg", "0", "active", "idle", is_leader=True)

    # WHEN _unit_name_text is called
    name = _unit_name_text(unit, "", "")

    # THEN the rendered plain text ends with '*'
    assert name.plain.endswith("*"), f"Expected '*' suffix, got: {name.plain!r}"


def test_unit_name_text_non_leader_has_no_star():
    # GIVEN a non-leader unit
    unit = UnitInfo("pg/1", "pg", "0", "active", "idle", is_leader=False)

    # WHEN _unit_name_text is called
    name = _unit_name_text(unit, "", "")

    # THEN the rendered text does not contain '*'
    assert "*" not in name.plain


def test_unit_name_text_leader_with_tree_prefix():
    # GIVEN a leader subordinate unit with a tree prefix
    unit = UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", is_leader=True, subordinate_of="pg/0")

    # WHEN _unit_name_text is called with a prefix
    name = _unit_name_text(unit, "└─ ", "")

    # THEN the text contains both the prefix and the '*' suffix
    assert "└─ " in name.plain
    assert name.plain.endswith("*")


@pytest.mark.asyncio
async def test_status_view_update_offers(pilot):
    # GIVEN a mounted StatusView where the offers panel is initially hidden
    view = StatusView(id="test-status-offers")
    await _mount_view(pilot, view)
    assert view.query_one("#status-offers-table").display is False

    # WHEN offers are updated with one offer
    view.update_offers(
        [
            OfferInfo(
                "cos",
                "alertmanager-karma-dashboard",
                "alertmanager",
                "alertmanager-k8s",
                180,
                "0/0",
                "karma-dashboard",
                "karma_dashboard",
                "provider",
            ),
        ]
    )
    await pilot.pause()

    # THEN the offers table is shown with one row
    assert view.query_one("#status-offers-table").display is True
    assert (
        view.query_one("#status-offers-table", ResourceTable).query_one("DataTable").row_count == 1
    )
    # Clearing offers hides the panel again
    view.update_offers([])
    await pilot.pause()
    assert view.query_one("#status-offers-table").display is False


def test_jujumate_header_breadcrumb():
    # GIVEN a HeaderContext with controller, model, counts, and connection info
    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(
        active_tab="tab-status",
        selected_controller="ck8s",
        selected_model="cos",
        app_count=6,
        unit_count=6,
        offer_count=3,
        relation_count=4,
        is_connected=True,
        timestamp="14:22:03",
    )

    # WHEN breadcrumb, stats, and status are built
    breadcrumb = header._build_breadcrumb(ctx)

    # THEN the breadcrumb contains controller and model names
    assert "ck8s" in breadcrumb
    assert "cos" in breadcrumb

    stats = header._build_stats(ctx)
    assert "6" in stats  # app_count
    assert "3" in stats  # offer_count
    assert "4" in stats  # relation_count

    status = header._build_status(ctx)
    assert "Live" in status
    assert "14:22:03" in status


@pytest.mark.parametrize(
    "tab, count_field, expected_key, expected_val",
    [
        pytest.param("tab-clouds", {"cloud_count": 3}, "clouds", "3", id="clouds"),
        pytest.param(
            "tab-controllers",
            {"controller_count": 2},
            "controllers",
            "2",
            id="controllers",
        ),
        pytest.param("tab-models", {"model_count": 5}, "models", "5", id="models"),
        pytest.param(
            "tab-status",
            {"machine_count": 3, "saas_count": 2},
            "3",
            "2",
            id="machine-and-saas",
        ),
        pytest.param("tab-unknown", {}, "", "", id="unknown-tab-empty"),
    ],
)
def test_jujumate_header_stats_by_tab(
    tab: str, count_field: dict, expected_key: str, expected_val: str
):
    # GIVEN a header and a tab/count combination
    header = JujuMateHeader.__new__(JujuMateHeader)

    # WHEN _build_stats is called
    ctx = HeaderContext(active_tab=tab, **count_field)
    result = header._build_stats(ctx)

    # THEN the matching key and count value appear in the result (or result is empty)
    if expected_key == "":
        assert result == ""
    else:
        assert expected_key in result
        assert expected_val in result


@pytest.mark.parametrize(
    "ctx_kwargs, expected_in, expected_not_in",
    [
        pytest.param(
            {"is_connected": False},
            ["Disconnected"],
            [],
            id="disconnected",
        ),
        pytest.param(
            {"is_connected": True, "timestamp": ""},
            ["Live"],
            ["·"],
            id="connected-no-timestamp",
        ),
    ],
)
def test_jujumate_header_build_status(ctx_kwargs, expected_in, expected_not_in):
    # GIVEN a HeaderContext with the given connection state
    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(**ctx_kwargs)

    # WHEN _build_status is called
    result = header._build_status(ctx)

    # THEN expected strings are present and absent
    for text in expected_in:
        assert text in result
    for text in expected_not_in:
        assert text not in result


@pytest.mark.parametrize(
    "ctx_kwargs, expected_in, expected_equal",
    [
        pytest.param({}, None, "", id="empty"),
        pytest.param({"juju_version": "3.6.0"}, ["3.6.0"], None, id="with-juju-version"),
    ],
)
def test_jujumate_header_build_breadcrumb(ctx_kwargs, expected_in, expected_equal):
    # GIVEN a HeaderContext with the given fields
    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(**ctx_kwargs)

    # WHEN _build_breadcrumb is called
    result = header._build_breadcrumb(ctx)

    # THEN the result matches expectations
    if expected_equal is not None:
        assert result == expected_equal
    for text in expected_in or []:
        assert text in result


@pytest.mark.parametrize(
    "text,expected,check_truncated",
    [
        pytest.param("", "", False, id="empty"),
        pytest.param("short", "short", False, id="short"),
        pytest.param("x" * (_MSG_TRUNC_WIDTH + 5), None, True, id="long"),
    ],
)
def test_trunc_msg(text, expected, check_truncated):
    # GIVEN a text string of varying length
    # WHEN _trunc_msg is called
    result = _trunc_msg(text)

    # THEN short strings are unchanged; long strings are truncated with an ellipsis
    if check_truncated:
        assert len(result) == _MSG_TRUNC_WIDTH
        assert result.endswith("…")
    else:
        assert result == expected


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_hidden_when_content_fits():
    # GIVEN a StatusView with a tall terminal and few apps
    app = JujuMateApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")])
        await pilot.pause()

        # WHEN _update_scroll_indicator is called
        view._update_scroll_indicator()
        indicator = view.query_one("#scroll-indicator")

        # THEN the scroll indicator is hidden because content fits
        assert indicator.display is False


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_shown_when_content_overflows():
    # GIVEN a StatusView with a very short terminal and many apps
    app = JujuMateApp()
    async with app.run_test(size=(120, 10)) as pilot:
        await pilot.pause()
        app.screen.query_one(TabbedContent).active = "tab-status"
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        many_apps = [
            AppInfo(f"app-{i}", "dev", f"app-{i}", "stable", 1, status="active") for i in range(20)
        ]
        view.update_apps(many_apps)
        await pilot.pause()
        await pilot.pause()

        # WHEN _update_scroll_indicator is called
        view._update_scroll_indicator()
        indicator = view.query_one("#scroll-indicator")

        # THEN the scroll indicator is shown because content overflows
        assert indicator.display is True


@pytest.mark.asyncio
async def test_tracked_scroll_notifies_parent():
    # GIVEN a StatusView with many apps causing overflow
    app = JujuMateApp()
    async with app.run_test(size=(120, 10)) as pilot:
        await pilot.pause()
        app.screen.query_one(TabbedContent).active = "tab-status"
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        many_apps = [
            AppInfo(f"app-{i}", "dev", f"app-{i}", "stable", 1, status="active") for i in range(20)
        ]
        view.update_apps(many_apps)
        await pilot.pause()
        await pilot.pause()

        # WHEN the tracked scroll watcher fires with scroll_y=0
        vs = view.query_one(_TrackedScroll)
        vs.watch_scroll_y(0.0)
        await pilot.pause()

        # THEN no exception is raised


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_handles_missing_widgets():
    """Cover defensive except branches when widgets aren't mounted."""
    # GIVEN a StatusView that is not mounted (no child widgets present)
    view = StatusView(id="test-detached")

    # WHEN _update_scroll_indicator and _watch__show_more are called
    # THEN no exception is raised
    view._update_scroll_indicator()
    view._watch__show_more(True)
    view._watch__show_more(False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id, machines, is_kubernetes, expected_display, expected_rows",
    [
        pytest.param(
            "test-status-machines",
            [
                MachineInfo(
                    "dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a"
                ),
                MachineInfo(
                    "dev", "1", "started", "10.0.0.2", "i-5678", "ubuntu@22.04", "us-east-1b"
                ),
            ],
            False,
            True,
            2,
            id="two-machines-visible",
        ),
        pytest.param(
            "test-status-machines-k8s",
            [MachineInfo("cos", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "")],
            True,
            False,
            None,
            id="kubernetes-hidden",
        ),
        pytest.param(
            "test-status-machines-empty",
            [],
            False,
            False,
            None,
            id="empty-hidden",
        ),
    ],
)
async def test_status_view_update_machines(
    pilot,
    view_id: str,
    machines: list,
    is_kubernetes: bool,
    expected_display: bool,
    expected_rows: int | None,
):
    # GIVEN a mounted StatusView
    view = StatusView(id=view_id)
    await _mount_view(pilot, view)

    # WHEN update_machines is called
    view.update_machines(machines, is_kubernetes=is_kubernetes)
    await pilot.pause()

    # THEN the machines table visibility and row count match expectations
    assert view.query_one("#status-machines-table").display is expected_display
    if expected_rows is not None:
        table = view.query_one("#status-machines-table", ResourceTable)
        assert table.query_one("DataTable").row_count == expected_rows


def test_colored_relation_no_colon():
    # GIVEN a relation string with no colon
    # WHEN _colored_relation is called
    result = _colored_relation("myapp")

    # THEN a Text object is returned unchanged
    assert isinstance(result, Text)
    assert str(result) == "myapp"


@pytest.mark.asyncio
async def test_status_view_msg_bar_updates_on_row_highlight(pilot):
    # GIVEN a StatusView with one app having a long message
    view = pilot.app.screen.query_one("#status-view", StatusView)
    long_msg = "unit is waiting for something to happen"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=long_msg)])
    await pilot.pause()
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    view._last_active_table = "status-apps-table"

    # WHEN a row highlight event fires for row 0
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )

    # THEN the msg-bar label shows the long message
    bar = view.query_one("#msg-bar", Label)
    assert long_msg in str(bar.render())


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_out_of_range(pilot):
    """Cover defensive path when cursor_row is out of range."""
    # GIVEN a StatusView with an empty _row_messages list
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view._row_messages.clear()
    dt = view.query_one("#status-apps-table DataTable", DataTable)

    # WHEN a stale highlight event fires with an out-of-range row index
    # THEN no exception is raised
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=99, row_key=None)  # type: ignore
    )


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_bad_parent(pilot):
    """Cover except branch when data_table.parent has no id."""
    # GIVEN a StatusView and a mock DataTable whose parent is None
    view = pilot.app.screen.query_one("#status-view", StatusView)
    bad_dt = MagicMock()
    bad_dt.parent = None  # triggers AttributeError on .id

    # WHEN a highlight event fires with the bad DataTable
    # THEN no exception is raised
    event = DataTable.RowHighlighted(
        data_table=bad_dt,
        cursor_row=0,
        row_key=RowKey("k"),  # type: ignore
    )
    view.on_data_table_row_highlighted(event)


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_negative_cursor_row_on_empty_table(pilot):
    """Regression test for IndexError when navigating an empty table (cursor_row=-1)."""
    # GIVEN a StatusView with no apps loaded (empty table)
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view._row_messages["status-apps-table"] = []
    view._last_active_table = "status-apps-table"
    dt = view.query_one("#status-apps-table DataTable", DataTable)

    # WHEN a highlight event fires with cursor_row=-1 (Textual emits this on empty tables)
    # THEN no IndexError is raised
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=-1, row_key=None)  # type: ignore
    )


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_missing_label():
    """Cover except branch when #msg-bar is not yet mounted."""
    # GIVEN a detached StatusView (no #msg-bar widget)
    view = StatusView(id="detached-msg-bar")
    dt_mock = type(
        "FakeDT", (), {"parent": type("FakeParent", (), {"id": "status-apps-table"})()}
    )()

    # WHEN a highlight event fires
    # THEN no exception is raised
    event = DataTable.RowHighlighted(data_table=dt_mock, cursor_row=0, row_key=None)  # type: ignore
    view.on_data_table_row_highlighted(event)


def test_restore_cursor_handles_unmounted():
    """Cover except branch of _restore_cursor when widget is not mounted."""
    # GIVEN a detached StatusView
    view = StatusView(id="detached-restore")

    # WHEN _restore_cursor is called with an arbitrary table id and row
    # THEN no exception is raised
    view._restore_cursor("status-apps-table", 5)


@pytest.mark.asyncio
async def test_restore_cursor_moves_datatable_cursor(pilot):
    """Cover _restore_cursor moving cursor to last-known position."""
    # GIVEN a StatusView with three apps and a saved cursor position of 2
    view = pilot.app.screen.query_one("#status-view", StatusView)
    msgs = ["msg0", "msg1", "msg2"]
    apps = [AppInfo(f"app{i}", "", f"app{i}", "stable", 1, message=msgs[i]) for i in range(3)]
    view.update_apps(apps)
    await pilot.pause()
    view._last_cursor["status-apps-table"] = 2

    # WHEN _restore_cursor is called
    view._restore_cursor("status-apps-table", 3)
    await pilot.pause()

    # THEN the DataTable cursor is moved to row 2
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    assert dt.cursor_row == 2


@pytest.mark.asyncio
async def test_row_highlighted_updates_msg_bar(pilot):
    """Cover on_data_table_row_highlighted updating msg-bar on user navigation."""
    # GIVEN a StatusView with an app whose message should appear in msg-bar
    view = pilot.app.screen.query_one("#status-view", StatusView)
    msg = "hook failed: unit not ready"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=msg)])
    await pilot.pause()
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    view._last_active_table = "status-apps-table"

    # WHEN a highlight event fires for row 0
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )

    # THEN the msg-bar label contains the app's message
    bar = view.query_one("#msg-bar", Label)
    assert msg in str(bar.render())


@pytest.mark.asyncio
async def test_inactive_table_event_ignored_by_handler(pilot):
    """Events from non-active tables must not overwrite the msg-bar."""
    # GIVEN a StatusView with apps and machines, msg-bar set to a sentinel value
    view = pilot.app.screen.query_one("#status-view", StatusView)
    apps = [AppInfo("myapp", "", "myapp", "stable", 1, message="hook failed")]
    machines = [MachineInfo("m", "0", "running", "", "", "", "", message="running")]
    view.update_apps(apps)
    view.update_machines(machines)
    await pilot.pause()
    bar = view.query_one("#msg-bar", Label)
    bar.update("sentinel")

    # WHEN a refresh event fires from the machines table while the user is on apps
    view._last_active_table = "status-apps-table"
    dt = view.query_one("#status-machines-table DataTable", DataTable)
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )

    # THEN the msg-bar is not overwritten
    assert "sentinel" in str(bar.render())


@pytest.mark.asyncio
async def test_table_focused_message_updates_active_table(pilot):
    """on_resource_table_table_focused sets _last_active_table and updates msg-bar."""
    # GIVEN a StatusView with one app
    view = pilot.app.screen.query_one("#status-view", StatusView)
    msg = "hook failed: timeout"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=msg)])
    await pilot.pause()

    # WHEN on_resource_table_table_focused fires for the apps table
    rt = view.query_one("#status-apps-table", ResourceTable)
    view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))

    # THEN _last_active_table is updated and msg-bar shows the message
    assert view._last_active_table == "status-apps-table"
    bar = view.query_one("#msg-bar", Label)
    assert msg in str(bar.render())


@pytest.mark.asyncio
async def test_table_focused_message_no_id_is_safe(pilot):
    """on_resource_table_table_focused with a table that has no id does not crash."""
    # GIVEN a StatusView and a ResourceTable without an id
    view = pilot.app.screen.query_one("#status-view", StatusView)
    rt = ResourceTable(columns=[Column("X", "x")])

    # WHEN on_resource_table_table_focused fires
    # THEN no exception is raised
    view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))


# ─────────────────────────────────────────────────────────────────────────────
# AppsView
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id, apps, expected_rows",
    [
        pytest.param(
            "test-apps",
            [
                AppInfo("pg", "dev", "postgresql", "14/stable", 363, unit_count=1, status="active"),
                AppInfo("mysql", "dev", "mysql", "8/stable", 100, unit_count=2, status="blocked"),
            ],
            2,
            id="two-apps",
        ),
        pytest.param("test-apps-empty", [], 0, id="empty"),
    ],
)
async def test_apps_view_update(pilot, view_id: str, apps: list, expected_rows: int):
    # GIVEN a mounted AppsView
    view = AppsView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()

    # WHEN update is called
    view.update(apps)
    await pilot.pause()

    # THEN the DataTable has the expected number of rows
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == expected_rows


@pytest.mark.asyncio
async def test_apps_view_row_selection_posts_app_selected(pilot):
    # GIVEN a mounted AppsView with one app
    view = AppsView(id="test-apps-sel")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([AppInfo("pg", "dev", "postgresql", "14/stable", 363)])
    await pilot.pause()

    # WHEN a row selection event fires
    with _capture_posted(view) as posted:
        dt = view.query_one(ResourceTable).query_one("DataTable")
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("dev/pg"))
        )

    # THEN an AppSelected message is posted with the correct name
    assert len(posted) == 1
    assert isinstance(posted[0], AppsView.AppSelected)
    assert posted[0].name == "dev/pg"


@pytest.mark.asyncio
async def test_apps_view_row_selection_ignores_none_key(pilot):
    # GIVEN a mounted AppsView with one app
    view = AppsView(id="test-apps-none")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([AppInfo("pg", "dev", "postgresql", "14/stable", 363)])
    await pilot.pause()

    # WHEN a row selection event fires with a None row key
    with _capture_posted(view) as posted:
        dt = view.query_one(ResourceTable).query_one("DataTable")
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey(None))
        )

    # THEN no message is posted
    assert posted == []


# ─────────────────────────────────────────────────────────────────────────────
# UnitsView
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id, units, expected_rows",
    [
        pytest.param(
            "test-units",
            [
                UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1"),
                UnitInfo("pg/1", "pg", "1", "active", "idle", "10.0.0.2"),
            ],
            2,
            id="two-units",
        ),
        pytest.param("test-units-empty", [], 0, id="empty"),
    ],
)
async def test_units_view_update(pilot, view_id: str, units: list, expected_rows: int):
    # GIVEN a mounted UnitsView
    view = UnitsView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()

    # WHEN update is called
    view.update(units)
    await pilot.pause()

    # THEN the DataTable has the expected number of rows
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == expected_rows


# ─────────────────────────────────────────────────────────────────────────────
# NavigableTable — cursor navigation & Enter key
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_navigable_table_cursor_navigation(pilot):
    # GIVEN a mounted NavigableTable with three rows
    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-nav")
    await pilot.app.screen.mount(nt)
    await pilot.pause()
    nt.update_rows([("row0",), ("row1",), ("row2",)], keys=["k0", "k1", "k2"])
    await pilot.pause()

    # WHEN cursor down/up actions are called
    assert nt._cursor == 0
    nt.action_cursor_down()
    assert nt._cursor == 1
    nt.action_cursor_down()
    assert nt._cursor == 2
    nt.action_cursor_down()  # at end — stays
    assert nt._cursor == 2
    nt.action_cursor_up()
    assert nt._cursor == 1
    nt.action_cursor_up()
    assert nt._cursor == 0
    nt.action_cursor_up()  # at start — stays

    # THEN the cursor stays within bounds
    assert nt._cursor == 0


@pytest.mark.asyncio
async def test_navigable_table_enter_posts_row_selected(pilot):
    # GIVEN a mounted NavigableTable with two rows and cursor at row 1
    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-enter")
    await pilot.app.screen.mount(nt)
    await pilot.pause()
    nt.update_rows([("row0",), ("row1",)], keys=["key0", "key1"])
    nt._cursor = 1

    # WHEN the select_row action fires (bound to Enter)
    with _capture_posted(nt) as posted:
        nt.action_select_row()

    # THEN a RowSelected message is posted with the key for row 1
    assert len(posted) == 1
    assert isinstance(posted[0], NavigableTable.RowSelected)
    assert posted[0].key == "key1"


@pytest.mark.asyncio
async def test_navigable_table_enter_no_rows_does_nothing(pilot):
    # GIVEN a mounted NavigableTable with no rows
    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-norow")
    await pilot.app.screen.mount(nt)

    # WHEN the select_row action fires (bound to Enter)
    with _capture_posted(nt) as posted:
        nt.action_select_row()

    # THEN no message is posted
    assert posted == []


@pytest.mark.asyncio
async def test_resource_table_table_focused_event_posts_message(pilot):
    # GIVEN a mounted ResourceTable
    view = ResourceTable(columns=[Column("Name", "name")], id="test-rt-focus")
    await _mount_view(pilot, view)

    with _capture_posted(view) as posted:
        # WHEN the internal DataTable receives focus
        pilot.app.screen.set_focus(view.query_one(DataTable))
        await pilot.pause()

    # THEN a TableFocused message is posted
    assert any(isinstance(m, ResourceTable.TableFocused) for m in posted)


@pytest.mark.asyncio
async def test_resource_table_collapsed_hides_datatable(pilot):
    # GIVEN a mounted ResourceTable with a row
    view = ResourceTable(columns=[Column("Name", "name")], id="test-rt-collapse")
    await _mount_view(pilot, view)
    view.update_rows([("pg",)])
    await pilot.pause()

    # WHEN collapsed is set to True
    view.collapsed = True
    await pilot.pause()

    # THEN DataTable is hidden, the widget becomes focusable, and focus moves to it
    assert view.query_one(DataTable).display is False
    assert view.can_focus is True
    assert "collapsed" in view.classes
    assert pilot.app.focused is view


@pytest.mark.asyncio
async def test_resource_table_expanded_shows_datatable(pilot):
    # GIVEN a collapsed ResourceTable
    view = ResourceTable(columns=[Column("Name", "name")], id="test-rt-expand")
    await _mount_view(pilot, view)
    view.update_rows([("pg",)])
    view.collapsed = True
    await pilot.pause()

    # WHEN collapsed is set back to False
    view.collapsed = False
    await pilot.pause()

    # THEN DataTable is visible, widget is no longer focusable, focus moves to DataTable
    assert view.query_one(DataTable).display is True
    assert view.can_focus is False
    assert "collapsed" not in view.classes
    assert pilot.app.focused is view.query_one(DataTable)


@pytest.mark.asyncio
async def test_resource_table_on_focus_when_collapsed_posts_table_focused(pilot):
    # GIVEN a collapsed ResourceTable (can_focus=True)
    view = ResourceTable(columns=[Column("Name", "name")], id="test-rt-focus-collapsed")
    await _mount_view(pilot, view)
    view.collapsed = True
    await pilot.pause()

    with _capture_posted(view) as posted:
        # WHEN the ResourceTable itself receives focus (collapsed state)
        view._on_focus(MagicMock())
        await pilot.pause()

    # THEN a TableFocused message is posted
    assert any(isinstance(m, ResourceTable.TableFocused) for m in posted)


# ─────────────────────────────────────────────────────────────────────────────
# StatusView — filter, row selection, messages, saas
# ─────────────────────────────────────────────────────────────────────────────


def test_group_units_with_orphan_subordinates():
    # GIVEN a principal, a known subordinate, and an orphan subordinate
    principal = UnitInfo("pg/0", "pg", "0", "active", "idle")
    sub_known = UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", subordinate_of="pg/0")
    sub_orphan = UnitInfo("lldp/0", "lldp", "0", "active", "idle", subordinate_of="missing/0")

    # WHEN _group_units is called with all three
    result = _group_units([principal, sub_known, sub_orphan])

    # THEN principal has no prefix, subordinates have the tree prefix
    assert result[0] == (principal, "")
    assert result[1] == (sub_known, "└─ ")
    assert result[2] == (sub_orphan, "└─ ")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id, saas_list, expected_display",
    [
        pytest.param(
            "test-saas-show",
            [SAASInfo("dev", "remote-pg", "active", "my-store", "my-store:admin/pg")],
            True,
            id="with-data-visible",
        ),
        pytest.param("test-saas-empty", [], False, id="empty-hidden"),
    ],
)
async def test_status_view_update_saas(
    pilot, view_id: str, saas_list: list, expected_display: bool
):
    # GIVEN a mounted StatusView
    view = StatusView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()

    # WHEN update_saas is called
    view.update_saas(saas_list)
    await pilot.pause()

    # THEN the SAAS table visibility matches expectations
    assert view.query_one("#status-saas-table").display is expected_display


@pytest.mark.asyncio
async def test_status_view_filter_activate_and_close(pilot):
    # GIVEN a StatusView where the filter bar is not visible
    view = pilot.app.screen.query_one("#status-view", StatusView)
    bar = view.query_one("#filter-bar")
    assert "visible" not in bar.classes

    # WHEN the filter is activated
    view.action_activate_filter()
    await pilot.pause()
    assert "visible" in bar.classes

    # WHEN the filter is closed
    view._filter = "pg"
    view.action_close_filter()
    await pilot.pause()

    # THEN the filter bar is hidden and the filter is cleared
    assert "visible" not in bar.classes
    assert view._filter == ""


@pytest.mark.asyncio
async def test_status_view_filter_filters_apps(pilot):
    # GIVEN a StatusView with two apps
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps(
        [
            AppInfo("postgresql", "dev", "postgresql", "14/stable", 1, status="active"),
            AppInfo("wordpress", "dev", "wordpress", "stable", 1, status="active"),
        ]
    )
    await pilot.pause()
    assert view.query_one("#status-apps-table DataTable").row_count == 2

    # WHEN a filter matching only one app is applied
    view._filter = "postgres"
    view._rerender_all()
    await pilot.pause()

    # THEN only the matching app is shown
    assert view.query_one("#status-apps-table DataTable").row_count == 1

    # WHEN the filter is cleared
    view._filter = ""
    view._rerender_all()
    await pilot.pause()

    # THEN all apps are shown again
    assert view.query_one("#status-apps-table DataTable").row_count == 2


@pytest.mark.asyncio
async def test_status_view_filter_filters_relations(pilot):
    # GIVEN a StatusView with two relations
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_relations(
        [
            RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular"),
            RelationInfo("dev", "mysql:db", "wp:db", "mysql", "regular"),
        ]
    )
    await pilot.pause()

    # WHEN a filter matching only the mysql relation is applied
    view._filter = "mysql"
    view._render_relations()
    await pilot.pause()

    # THEN only the mysql relation is shown
    assert view.query_one("#status-rels-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_peer_relations_hidden_by_default(pilot):
    # GIVEN a StatusView with one peer and one regular relation
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_relations(
        [
            RelationInfo("dev", "pg:pg", "pg:pg", "pgsql", "peer"),
            RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular"),
        ]
    )
    await pilot.pause()

    # WHEN no toggle has been pressed (default state)
    # THEN only the regular relation is shown
    assert view._show_peer_relations is False
    assert view.query_one("#status-rels-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_action_toggle_peer_relations_shows_and_hides(pilot):
    # GIVEN a StatusView with one peer and one regular relation
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_relations(
        [
            RelationInfo("dev", "pg:pg", "pg:pg", "pgsql", "peer"),
            RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular"),
        ]
    )
    await pilot.pause()
    dt = view.query_one("#status-rels-table DataTable")
    assert dt.row_count == 1

    # WHEN action_toggle_peer_relations is called
    view.action_toggle_peer_relations()
    await pilot.pause()

    # THEN both relations are shown
    assert dt.row_count == 2
    assert view._show_peer_relations is True

    # WHEN action_toggle_peer_relations is called again
    view.action_toggle_peer_relations()
    await pilot.pause()

    # THEN peer relations are hidden again
    assert dt.row_count == 1
    assert view._show_peer_relations is False


@pytest.mark.asyncio
async def test_status_view_units_in_machines_hidden_by_default(pilot):
    # GIVEN a StatusView with one machine and one unit
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_machines(
        [MachineInfo("dev", "0", "running", "10.0.0.1", "i-abc", "ubuntu@22.04", "us-east-1a")],
        is_kubernetes=False,
    )
    view.update_units([UnitInfo("pg/0", "pg", "0", "active", "idle")], is_kubernetes=False)
    await pilot.pause()

    # WHEN no toggle has been pressed (default state)
    # THEN the machines table shows only 1 row (the machine, not the unit)
    assert view._show_units_in_machines is False
    assert view.query_one("#status-machines-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_action_toggle_units_in_machines_shows_and_hides(pilot):
    # GIVEN a StatusView with one machine and two units assigned to it
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_machines(
        [MachineInfo("dev", "0", "running", "10.0.0.1", "i-abc", "ubuntu@22.04", "us-east-1a")],
        is_kubernetes=False,
    )
    view.update_units(
        [
            UnitInfo("pg/0", "pg", "0", "active", "idle"),
            UnitInfo("wp/0", "wordpress", "0", "active", "idle"),
        ],
        is_kubernetes=False,
    )
    await pilot.pause()
    dt = view.query_one("#status-machines-table DataTable")
    assert dt.row_count == 1

    # WHEN action_toggle_units_in_machines is called
    view.action_toggle_units_in_machines()
    await pilot.pause()

    # THEN the machine row plus its two units are shown (3 rows total)
    assert dt.row_count == 3
    assert view._show_units_in_machines is True

    # WHEN action_toggle_units_in_machines is called again
    view.action_toggle_units_in_machines()
    await pilot.pause()

    # THEN only the machine row is shown again
    assert dt.row_count == 1
    assert view._show_units_in_machines is False


@pytest.mark.asyncio
async def test_status_view_action_toggle_collapse_collapses_active_panel(pilot):
    # GIVEN a StatusView with the apps table as the last active table
    view = pilot.app.screen.query_one("#status-view", StatusView)
    rt = view.query_one("#status-apps-table", ResourceTable)
    view._last_active_table = "status-apps-table"
    await pilot.pause()

    # WHEN action_toggle_collapse is called
    view.action_toggle_collapse()
    await pilot.pause()

    # THEN the apps ResourceTable is collapsed
    assert rt.collapsed is True
    assert rt.query_one(DataTable).display is False


@pytest.mark.asyncio
async def test_status_view_action_toggle_collapse_expands_collapsed_panel(pilot):
    # GIVEN a collapsed apps panel as the active table
    view = pilot.app.screen.query_one("#status-view", StatusView)
    rt = view.query_one("#status-apps-table", ResourceTable)
    view._last_active_table = "status-apps-table"
    rt.collapsed = True
    await pilot.pause()

    # WHEN action_toggle_collapse is called again
    view.action_toggle_collapse()
    await pilot.pause()

    # THEN the apps ResourceTable is expanded
    assert rt.collapsed is False
    assert rt.query_one(DataTable).display is True


@pytest.mark.asyncio
async def test_status_view_action_toggle_collapse_no_active_table_is_noop(pilot):
    # GIVEN no active table is set
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view._last_active_table = ""

    # WHEN action_toggle_collapse is called
    view.action_toggle_collapse()
    await pilot.pause()

    # THEN no panel is collapsed (all remain expanded)
    for rt in view.query(ResourceTable):
        assert rt.collapsed is False


@pytest.mark.asyncio
async def test_resource_table_watch_collapsed_before_mount_is_safe(pilot):
    # GIVEN a ResourceTable that is not yet mounted (query_one will raise)
    view = ResourceTable(columns=[Column("Name", "name")], id="test-rt-premount")

    # WHEN collapsed is set before mounting (watch fires, query_one fails)
    # THEN no exception is raised
    view._watch_collapsed(True)


@pytest.mark.asyncio
async def test_status_view_action_toggle_collapse_invalid_id_is_safe(pilot):
    # GIVEN a StatusView with a _last_active_table pointing to a nonexistent widget
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view._last_active_table = "nonexistent-table-id"

    # WHEN action_toggle_collapse is called
    # THEN no exception is raised
    view.action_toggle_collapse()
    await pilot.pause()


@pytest.mark.asyncio
async def test_status_view_units_in_machines_includes_subordinates_nested(pilot):
    # GIVEN a machine with one principal and one subordinate unit
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_machines(
        [MachineInfo("dev", "0", "running", "10.0.0.1", "i-abc", "ubuntu@22.04", "us-east-1a")],
        is_kubernetes=False,
    )
    view.update_units(
        [
            UnitInfo("pg/0", "pg", "0", "active", "idle"),
            UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", subordinate_of="pg/0"),
        ],
        is_kubernetes=False,
    )
    view._show_units_in_machines = True
    view._render_machines()
    await pilot.pause()

    # THEN machine + principal + subordinate all appear (3 rows total)
    assert view.query_one("#status-machines-table DataTable").row_count == 3


def test_group_units_by_machine_tree_prefixes():
    # GIVEN one machine with two principals: pg/0 (has sub nrpe/0) and wp/0 (no subs)
    m0 = MachineInfo("dev", "0", "running", "", "", "", "")
    pg = UnitInfo("pg/0", "pg", "0", "active", "idle")
    nrpe = UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", subordinate_of="pg/0")
    wp = UnitInfo("wp/0", "wordpress", "0", "active", "idle")

    # WHEN _group_units_by_machine is called
    result = _group_units_by_machine([m0], [pg, nrpe, wp])

    # THEN: machine / pg/0 (├─, non-last) / nrpe/0 (│  └─) / wp/0 (└─, last, no subs)
    items = [(type(item).__name__, prefix) for item, prefix in result]
    assert items == [
        ("MachineInfo", ""),
        ("UnitInfo", "├─ "),  # pg/0, non-last principal
        ("UnitInfo", "│  └─ "),  # nrpe/0, last sub under non-last principal
        ("UnitInfo", "└─ "),  # wp/0, last principal (no subs)
    ]


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update_fn, entities, table_id, msg_class, attr_chain, expected_val, setup_kwargs",
    [
        pytest.param(
            "update_apps",
            [AppInfo("pg", "dev", "pg", "14/stable", 1)],
            "#status-apps-table",
            StatusView.AppSelected,
            ["app", "name"],
            "pg",
            {},
            id="app",
        ),
        pytest.param(
            "update_relations",
            [RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")],
            "#status-rels-table",
            StatusView.RelationSelected,
            ["relation", "interface"],
            "pgsql",
            {},
            id="relation",
        ),
        pytest.param(
            "update_offers",
            [
                OfferInfo(
                    "cos",
                    "alertmanager-karma-dashboard",
                    "alertmanager",
                    "alertmanager-k8s",
                    180,
                    "0/0",
                    "karma-dashboard",
                    "karma_dashboard",
                    "provider",
                )
            ],
            "#status-offers-table",
            StatusView.OfferSelected,
            ["offer", "name"],
            "alertmanager-karma-dashboard",
            {},
            id="offer",
        ),
        pytest.param(
            "update_machines",
            [
                MachineInfo(
                    "dev", "0", "started", "10.0.0.1", "i-abc123", "ubuntu@22.04", "us-east-1a"
                )
            ],
            "#status-machines-table",
            StatusView.MachineSelected,
            ["machine", "id"],
            "0",
            {"is_kubernetes": False},
            id="machine",
        ),
    ],
)
async def test_status_view_row_selected_posts_message(
    pilot,
    update_fn: str,
    entities: list,
    table_id: str,
    msg_class: type,
    attr_chain: list,
    expected_val: object,
    setup_kwargs: dict,
):
    # GIVEN a StatusView populated with the entity under test
    view = pilot.app.screen.query_one("#status-view", StatusView)
    getattr(view, update_fn)(entities, **setup_kwargs)
    await pilot.pause()

    # WHEN a row is selected in the corresponding table
    with _capture_posted(view) as posted:
        dt = view.query_one(f"{table_id} DataTable", DataTable)
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("k"))
        )

    # THEN one message of the correct type is posted with the expected attribute value
    assert len(posted) == 1
    assert isinstance(posted[0], msg_class)
    obj: object = posted[0]
    for attr in attr_chain:
        obj = getattr(obj, attr)
    assert obj == expected_val


@pytest.mark.asyncio
async def test_status_view_check_action_close_filter(pilot):
    # GIVEN a StatusView with various filter bar and _filter states
    view = pilot.app.screen.query_one("#status-view", StatusView)
    bar = view.query_one("#filter-bar")

    bar.remove_class("visible")
    view._filter = ""
    # WHEN filter bar is hidden and filter is empty
    # THEN close_filter action is disabled
    assert view.check_action("close_filter", ()) is False

    bar.add_class("visible")
    # WHEN filter bar is visible
    # THEN close_filter action is enabled
    assert view.check_action("close_filter", ()) is True

    bar.remove_class("visible")
    view._filter = "pg"
    # WHEN filter bar is hidden but filter has text
    # THEN close_filter action is still enabled
    assert view.check_action("close_filter", ()) is True

    # THEN activate_filter is always enabled
    assert view.check_action("activate_filter", ()) is True


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_with_data(pilot):
    # GIVEN a StatusView populated with apps and relations
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")])
    view.update_relations([RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")])
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the result contains app and relation section headers
    assert "Applications" in result
    assert "Integrations" in result
    assert "pg" in result


@pytest.mark.asyncio
async def test_status_view_action_copy_to_clipboard_with_data(pilot):
    # GIVEN a StatusView with apps loaded
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")])
    await pilot.pause()
    _mock_clipboard(view)

    # WHEN action_copy_to_clipboard is called
    view.action_copy_to_clipboard()

    # THEN copy_to_clipboard is called with a non-empty string
    view.app.copy_to_clipboard.assert_called_once()
    args = view.app.copy_to_clipboard.call_args[0]
    assert len(args[0]) > 0


@pytest.mark.asyncio
async def test_status_view_action_copy_to_clipboard_empty_notifies(pilot):
    # GIVEN a StatusView with no data
    view = StatusView(id="test-sv-empty-copy")
    await _mount_view(pilot, view)
    view.notify = MagicMock()

    # WHEN action_copy_to_clipboard is called on the empty view
    view.action_copy_to_clipboard()

    # THEN notify is called with a warning
    view.notify.assert_called_once_with("Nothing to copy", severity="warning")


# ─────────────────────────────────────────────────────────────────────────────
# AppConfigView — pure helpers + mounted widget
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ai,entries",
    [
        pytest.param(
            AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active"),
            [
                AppConfigEntry("log-level", "DEBUG", "INFO", "string", "Log level", "user"),
                AppConfigEntry("port", "5432", "5432", "int", "Port", "default"),
            ],
            id="with-changed-values",
        ),
        pytest.param(
            AppInfo("pg", "dev", "pg", "", 363),
            [],
            id="empty-entries",
        ),
    ],
)
def test_build_config_renderable(ai, entries):
    # GIVEN an AppInfo and a list of config entries
    # WHEN _build_config_renderable is called
    # THEN a Rich Table is returned
    assert isinstance(_build_config_renderable(entries), Table)


@pytest.mark.parametrize(
    "ai,entries,expected_fragments",
    [
        pytest.param(
            AppInfo("pg", "dev", "postgresql", "14/stable", 363),
            [
                AppConfigEntry("log-level", "DEBUG", "INFO", "string", "Log level", "user"),
                AppConfigEntry("port", "5432", "5432", "int", "Port", "default"),
            ],
            ["pg", "log-level: DEBUG", "port: 5432"],
            id="with-changed",
        ),
        pytest.param(
            AppInfo("pg", "dev", "postgresql", "14/stable", 363),
            [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")],
            ["(none)"],
            id="no-changed",
        ),
        pytest.param(
            AppInfo("pg", "dev", "postgresql", "14/stable", 363),
            [AppConfigEntry("log-level", "DEBUG", "INFO", "string", "Log level", "user")],
            ["default: INFO"],
            id="changed-with-default-diff",
        ),
    ],
)
def test_format_plain_text_app_config(ai, entries, expected_fragments):
    # GIVEN an AppInfo and config entries with varying change states
    # WHEN _format_plain_text is called
    result = _ac_format_plain_text(ai, entries)

    # THEN all expected fragments are present in the output
    for fragment in expected_fragments:
        assert fragment in result


@pytest.mark.asyncio
async def test_app_config_view_update(pilot):
    # GIVEN a mounted AppConfigView
    view = AppConfigView(id="test-ac")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]

    # WHEN update is called with an app and config entries
    view.update(ai, entries)
    await pilot.pause()

    # THEN the config panel is shown and the empty placeholder is hidden
    assert view.query_one("#ac-panel").display is True
    assert view.query_one("#ac-empty").display is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id,method_name,method_args",
    [
        pytest.param(
            "test-ac-load",
            "show_loading",
            [AppInfo("pg", "dev", "pg", "", 1)],
            id="loading",
        ),
        pytest.param(
            "test-ac-err",
            "show_error",
            [AppInfo("pg", "dev", "pg", "", 1), "connection refused"],
            id="error",
        ),
    ],
)
async def test_app_config_view_visibility_states(pilot, view_id, method_name, method_args):
    # GIVEN a mounted AppConfigView
    view = AppConfigView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()

    # WHEN a loading or error state method is called
    getattr(view, method_name)(*method_args)
    await pilot.pause()

    # THEN the empty placeholder is shown and the config panel is hidden
    assert view.query_one("#ac-empty").display is True
    assert view.query_one("#ac-panel").display is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "has_app",
    [
        pytest.param(False, id="no-app"),
        pytest.param(True, id="with-app"),
    ],
)
async def test_app_config_view_copy_to_clipboard(pilot, has_app):
    # GIVEN a mounted AppConfigView, optionally updated with an app
    view = AppConfigView(id=f"test-ac-copy-{'app' if has_app else 'noapp'}")
    await _mount_view(pilot, view)
    if has_app:
        ai = AppInfo("pg", "dev", "postgresql", "14/stable", 1, status="active")
        entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
        view.update(ai, entries)
        await pilot.pause()

    _mock_clipboard(view)

    # WHEN action_copy_to_clipboard is called
    view.action_copy_to_clipboard()

    # THEN the correct method is called based on whether an app is loaded
    if has_app:
        view.app.copy_to_clipboard.assert_called_once()
        args = view.app.copy_to_clipboard.call_args[0]
        assert len(args[0]) > 0
    else:
        view.notify.assert_called_once_with("No config to copy", severity="warning")
        view.app.copy_to_clipboard.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# RelationDataView — pure helpers + mounted widget
# ─────────────────────────────────────────────────────────────────────────────


def test_kv_table_with_data():
    # GIVEN a non-empty dict
    # WHEN _kv_table is called
    # THEN the resulting table has one row per key
    assert _kv_table({"key1": "value1", "key2": "value2"}).row_count == 2


def test_kv_table_empty():
    # GIVEN an empty dict
    # WHEN _kv_table is called
    # THEN the resulting table has one placeholder row
    assert _kv_table({}).row_count == 1  # <empty> row


def test_unit_panel_with_leader():
    # GIVEN unit name, data, leader flag, and a color
    # WHEN _unit_panel is called
    # THEN a Rich Panel is returned
    assert isinstance(_unit_panel("pg/0", {"key": "val"}, is_leader=True, color="#77216F"), Panel)


def test_unit_panel_non_leader():
    # GIVEN unit name, empty data, non-leader flag, and a color
    # WHEN _unit_panel is called
    # THEN a Rich Panel is returned
    assert isinstance(_unit_panel("pg/1", {}, is_leader=False, color="#E95420"), Panel)


@pytest.mark.parametrize(
    "rel,entries",
    [
        pytest.param(
            RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular", relation_id=5),
            [
                RelationDataEntry("provider", "postgresql", "host", "10.0.0.1", "app"),
                RelationDataEntry("requirer", "wordpress/0", "port", "5432", "unit"),
            ],
            id="regular",
        ),
        pytest.param(
            RelationInfo("dev", "etcd:cluster", "etcd:cluster", "etcd", "peer", relation_id=3),
            [RelationDataEntry("peer", "etcd", "h", "v", "app")],
            id="peer",
        ),
    ],
)
def test_build_relation_renderable(rel, entries):
    # GIVEN a RelationInfo and relation data entries
    # WHEN _build_relation_renderable is called
    # THEN a Rich Table is returned
    assert isinstance(_build_relation_renderable(rel, entries), Table)


@pytest.mark.parametrize(
    "rel,entries,expected_fragments",
    [
        pytest.param(
            RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular", relation_id=5),
            [
                RelationDataEntry("provider", "postgresql", "host", "10.0.0.1", "app"),
                RelationDataEntry("provider", "postgresql/0", "key", "val", "unit"),
            ],
            ["relation-id: 5", "host"],
            id="regular",
        ),
        pytest.param(
            RelationInfo("dev", "etcd:cluster", "etcd:cluster", "etcd", "peer", relation_id=3),
            [],
            ["peer", "<empty>"],
            id="peer",
        ),
        pytest.param(
            RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1),
            [],
            ["<empty>"],
            id="empty-entries",
        ),
    ],
)
def test_format_plain_text_relation(rel, entries, expected_fragments):
    # GIVEN a RelationInfo and optional entries
    # WHEN _format_plain_text is called
    result = _rd_format_plain_text(rel, entries)

    # THEN all expected fragments appear in the output
    for fragment in expected_fragments:
        assert fragment in result


@pytest.mark.asyncio
async def test_relation_data_view_update(pilot):
    # GIVEN a mounted RelationDataView
    view = RelationDataView(id="test-rd")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)

    # WHEN update is called with a relation and one data entry
    view.update(rel, [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")])
    await pilot.pause()

    # THEN the relation panel is shown and the empty placeholder is hidden
    assert view.query_one("#rd-panel").display is True
    assert view.query_one("#rd-empty").display is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_id,method_name,method_args",
    [
        pytest.param(
            "test-rd-load",
            "show_loading",
            [RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")],
            id="loading",
        ),
        pytest.param(
            "test-rd-err",
            "show_error",
            [RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular"), "timeout"],
            id="error",
        ),
    ],
)
async def test_relation_data_view_visibility_states(pilot, view_id, method_name, method_args):
    # GIVEN a mounted RelationDataView
    view = RelationDataView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()

    # WHEN a loading or error state method is called
    getattr(view, method_name)(*method_args)
    await pilot.pause()

    # THEN the empty placeholder is shown and the data panel is hidden
    assert view.query_one("#rd-empty").display is True
    assert view.query_one("#rd-panel").display is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "has_relation",
    [
        pytest.param(False, id="no-relation"),
        pytest.param(True, id="with-relation"),
    ],
)
async def test_relation_data_view_copy_to_clipboard(pilot, has_relation):
    # GIVEN a mounted RelationDataView, optionally updated with a relation
    view = RelationDataView(id=f"test-rd-copy-{'rel' if has_relation else 'norel'}")
    await _mount_view(pilot, view)
    if has_relation:
        rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
        entries = [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")]
        view.update(rel, entries)
        await pilot.pause()

    _mock_clipboard(view)

    # WHEN action_copy_to_clipboard is called
    view.action_copy_to_clipboard()

    # THEN the correct method is called based on whether a relation is loaded
    if has_relation:
        view.app.copy_to_clipboard.assert_called_once()
    else:
        view.notify.assert_called_once_with("No relation data to copy", severity="warning")
        view.app.copy_to_clipboard.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# StatusView — coverage of previously uncovered branches
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_row_highlighted_has_focus_sets_active_table(pilot):
    """Line 454: has_focus=True branch sets _last_active_table."""
    # GIVEN a StatusView with one app and a mock event with has_focus=True
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1)])
    await pilot.pause()

    mock_event = MagicMock()
    mock_event.data_table.has_focus = True
    mock_event.data_table.parent.id = "status-apps-table"
    mock_event.cursor_row = 0

    # WHEN on_data_table_row_highlighted fires
    view.on_data_table_row_highlighted(mock_event)

    # THEN _last_active_table is updated to the apps table
    assert view._last_active_table == "status-apps-table"


@pytest.mark.asyncio
async def test_status_view_resource_table_focused_exception_safe(pilot):
    """on_resource_table_table_focused: NoMatches from query_one is silently swallowed."""
    # GIVEN a StatusView and a broken event whose query_one raises NoMatches
    view = pilot.app.screen.query_one("#status-view", StatusView)

    broken_event = MagicMock()
    broken_event.resource_table.id = "status-apps-table"
    broken_event.resource_table.query_one = MagicMock(side_effect=NoMatches("broken"))

    # WHEN the handler is called
    # THEN no exception propagates
    view.on_resource_table_table_focused(broken_event)  # must not raise


@pytest.mark.asyncio
async def test_status_view_row_selected_exception_safe(pilot):
    """on_data_table_row_selected: AttributeError from data_table access is silently swallowed."""
    # GIVEN a StatusView and an event whose data_table property raises AttributeError
    view = pilot.app.screen.query_one("#status-view", StatusView)

    class _BadEvent:
        @property
        def data_table(self):
            raise AttributeError("bad table")

    # WHEN the handler is called with the bad event
    # THEN no exception propagates
    view.on_data_table_row_selected(_BadEvent())  # must not raise


@pytest.mark.asyncio
async def test_status_view_rerender_all_exception_safe(pilot):
    """_rerender_all: NoMatches from each render method is swallowed individually."""
    # GIVEN a StatusView where every render method raises NoMatches
    view = pilot.app.screen.query_one("#status-view", StatusView)

    with (
        patch.object(view, "_render_apps", side_effect=NoMatches),
        patch.object(view, "_render_saas", side_effect=NoMatches),
        patch.object(view, "_render_units", side_effect=NoMatches),
        patch.object(view, "_render_offers", side_effect=NoMatches),
        patch.object(view, "_render_machines", side_effect=NoMatches),
        patch.object(view, "_render_relations", side_effect=NoMatches),
    ):
        # WHEN _rerender_all is called
        # THEN no exception propagates
        view._rerender_all()  # must not raise


@pytest.mark.asyncio
async def test_status_view_check_action_close_filter_exception_safe(pilot):
    """check_action: NoMatches from query_one returns False instead of propagating."""
    # GIVEN a StatusView where query_one raises NoMatches
    view = pilot.app.screen.query_one("#status-view", StatusView)

    # WHEN check_action is called
    with patch.object(view, "query_one", side_effect=NoMatches("no widget")):
        result = view.check_action("close_filter", ())

    # THEN False is returned instead of propagating the exception
    assert result is False


@pytest.mark.asyncio
async def test_status_view_filter_changed_updates_filter(pilot):
    """Lines 583-584: Input.Changed on #filter-input sets _filter and rerenders."""
    # GIVEN a StatusView with two apps
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps(
        [
            AppInfo("postgresql", "dev", "postgresql", "14/stable", 1),
            AppInfo("wordpress", "dev", "wordpress", "stable", 1),
        ]
    )
    await pilot.pause()

    view.action_activate_filter()
    await pilot.pause()

    # WHEN the filter input value changes to "postgres"
    fi = view.query_one("#filter-input", Input)
    view._on_filter_changed(Input.Changed(input=fi, value="postgres"))
    await pilot.pause()

    # THEN _filter is updated and only matching apps are shown
    assert view._filter == "postgres"
    assert view.query_one("#status-apps-table DataTable", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_status_view_filter_submitted_hides_input(pilot):
    """Input.Submitted on #filter-input hides the filter bar."""
    # GIVEN a StatusView with the filter bar visible
    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.action_activate_filter()
    await pilot.pause()

    bar = view.query_one("#filter-bar")
    assert "visible" in bar.classes

    # WHEN the filter input is submitted
    fi = view.query_one("#filter-input", Input)
    view._on_filter_submitted(Input.Submitted(input=fi, value="pg"))
    await pilot.pause()

    # THEN the filter bar is hidden
    assert "visible" not in bar.classes


# ─────────────────────────────────────────────────────────────────────────────
# StatusView — _format_for_clipboard coverage gaps
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_header_section(pilot):
    """Lines 667-671: header section rendered when context fields are set."""
    # GIVEN a StatusView with context fields populated
    view = StatusView(id="test-sv-clipboard-header")
    await _mount_view(pilot, view)
    view._ctx_cloud = "aws"
    view._ctx_controller = "prod"
    view._ctx_model = "dev"
    view._ctx_juju_version = "3.6.0"

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the header fields appear in the output
    assert "Cloud:" in result
    assert "Controller:" in result
    assert "Model:" in result
    assert "Juju:" in result


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_saas_section(pilot):
    """Line 690: SAAS section rendered when SAAS entries are present."""
    # GIVEN a StatusView populated with a SAAS entry
    view = StatusView(id="test-sv-clipboard-saas")
    await _mount_view(pilot, view)
    view.update_saas([SAASInfo("dev", "prom-scrape", "active", "local", "admin/cos.prom")])
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the SAAS section header appears
    assert "SAAS" in result


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_kubernetes_units(pilot):
    """Lines 729-739: K8s units branch rendered when is_kubernetes=True."""
    # GIVEN a StatusView populated with a K8s unit
    view = StatusView(id="test-sv-clipboard-k8s")
    await _mount_view(pilot, view)
    view.update_units(
        [UnitInfo("pg/0", "pg", "", "active", "idle", address="10.0.0.1")],
        is_kubernetes=True,
    )
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the Units section appears
    assert "Units" in result


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_machines_section(pilot):
    """Line 757: Machines section rendered when machine entries are present."""
    # GIVEN a StatusView populated with a machine
    view = StatusView(id="test-sv-clipboard-machines")
    await _mount_view(pilot, view)
    view.update_machines(
        [MachineInfo("dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a")]
    )
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the Machines section appears
    assert "Machines" in result


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_offers_section(pilot):
    """Line 767: Offers section rendered when offer entries are present."""
    # GIVEN a StatusView populated with an offer
    view = StatusView(id="test-sv-clipboard-offers")
    await _mount_view(pilot, view)
    view.update_offers(
        [
            OfferInfo(
                "cos",
                "karma",
                "alertmanager",
                "alertmanager-k8s",
                180,
                "0/0",
                "karma-dashboard",
                "karma_dashboard",
                "provider",
            )
        ]
    )
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the Offers section appears
    assert "Offers" in result


# ─────────────────────────────────────────────────────────────────────────────
# JujuMateApp
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_switch_theme_unknown_does_not_change_theme(pilot):
    """Lines 69-70: switch_theme with an unknown name is a no-op."""
    # GIVEN a running JujuMateApp with an initial theme
    original_theme = pilot.app.theme

    # WHEN switch_theme is called with a nonexistent theme name
    pilot.app.switch_theme("nonexistent-xxxx")
    await pilot.pause()

    # THEN the app theme is unchanged
    assert pilot.app.theme == original_theme


# ─────────────────────────────────────────────────────────────────────────────
# JujuMateHeader — _tick_pulse
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jujumate_header_tick_pulse_toggles(pilot):
    """Lines 48-49: _tick_pulse toggles _pulse_on and calls update_context."""
    # GIVEN a JujuMateHeader mounted in the running app
    header = pilot.app.screen.query_one(JujuMateHeader)
    initial_pulse = header._pulse_on

    # WHEN _tick_pulse is called
    header._tick_pulse()
    await pilot.pause()

    # THEN _pulse_on is toggled
    assert header._pulse_on is not initial_pulse


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_iaas_units(pilot):
    # GIVEN a StatusView populated with IaaS units (is_kubernetes defaults to False)
    view = StatusView(id="test-sv-iaas-clip")
    await _mount_view(pilot, view)
    view.update_units(
        [UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1")],
        is_kubernetes=False,
    )
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the IaaS units section is included with Machine column header
    assert "Units" in result
    assert "Machine" in result


@pytest.mark.asyncio
async def test_status_view_row_selected_on_unit_row_does_not_post_machine_selected(pilot):
    # GIVEN a StatusView in units-per-machine mode with one machine and one unit
    view = pilot.app.screen.query_one("#status-view", StatusView)
    machine = MachineInfo(
        "dev", "0", "started", "10.0.0.1", "i-abc123", "ubuntu@22.04", "us-east-1a"
    )
    view.update_machines([machine], is_kubernetes=False)
    view.update_units([UnitInfo("pg/0", "pg", "0", "active", "idle")], is_kubernetes=False)
    view._show_units_in_machines = True
    view._render_machines()
    await pilot.pause()

    with _capture_posted(view) as posted:
        # WHEN a row is selected that corresponds to a unit (row index 1)
        dt = view.query_one("#status-machines-table DataTable", DataTable)
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=1, row_key=RowKey("k"))
        )

    # THEN no message is posted (unit rows are not selectable as machines)
    assert len(posted) == 0


# ---------------------------------------------------------------------------
# Storage panel tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_view_update_storage_shows_table(pilot):
    # GIVEN a mounted StatusView where the storage panel is initially hidden
    view = StatusView(id="test-status-storage")
    await _mount_view(pilot, view)
    assert view.query_one("#status-storage-table").display is False

    # WHEN storage is updated with one entry
    view.update_storage(
        [
            StorageInfo(
                storage_id="data/0",
                unit="mysql/0",
                kind="filesystem",
                pool="rootfs",
                location="/var/lib/juju/storage/data/0",
                size_mib=1024,
                status="attached",
                message="",
                persistent=True,
                life="alive",
                model="dev",
                controller="ctrl",
            )
        ]
    )
    await pilot.pause()

    # THEN the storage table is shown with one row
    assert view.query_one("#status-storage-table").display is True
    assert (
        view.query_one("#status-storage-table", ResourceTable).query_one("DataTable").row_count == 1
    )


@pytest.mark.asyncio
async def test_status_view_update_storage_hides_table_when_empty(pilot):
    # GIVEN a StatusView that already has a storage entry displayed
    view = StatusView(id="test-status-storage-hide")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            StorageInfo(
                storage_id="data/0",
                unit="mysql/0",
                kind="filesystem",
                pool="rootfs",
                location="/var/lib/juju/storage/data/0",
                size_mib=1024,
                status="attached",
                message="",
                persistent=True,
                life="alive",
                model="dev",
                controller="ctrl",
            )
        ]
    )
    await pilot.pause()
    assert view.query_one("#status-storage-table").display is True

    # WHEN storage is cleared
    view.update_storage([])
    await pilot.pause()

    # THEN the table is hidden again
    assert view.query_one("#status-storage-table").display is False


# ---------------------------------------------------------------------------
# _format_size_mib (status_view local copy)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mib, expected",
    [
        pytest.param(0, "", id="zero"),
        pytest.param(-1, "", id="negative"),
        pytest.param(512, "512 MiB", id="below-1-gib"),
    ],
)
def test_format_size_mib(mib: int, expected: str):
    # GIVEN a MiB integer
    # WHEN the status_view local _format_size_mib is called
    # THEN the result matches the expected human-readable string
    assert _format_size_mib(mib) == expected


# ---------------------------------------------------------------------------
# StorageSelected message
# ---------------------------------------------------------------------------


def test_storage_selected_message_holds_storage():
    # GIVEN a StorageInfo instance
    storage = StorageInfo(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="/mnt/data",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )

    # WHEN a StorageSelected message is instantiated
    msg = StatusView.StorageSelected(storage)

    # THEN the message holds the storage reference
    assert msg.storage is storage


# ---------------------------------------------------------------------------
# Storage row → StorageSelected posted on Enter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_view_storage_row_enter_posts_storage_selected(pilot):
    # GIVEN a StatusView with one storage entry
    view = StatusView(id="test-storage-selected")
    await _mount_view(pilot, view)
    storage = StorageInfo(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="/mnt/data",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )
    view.update_storage([storage])
    await pilot.pause()

    # WHEN a row is selected in the storage table
    with _capture_posted(view) as posted:
        dt = view.query_one("#status-storage-table DataTable", DataTable)
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("k"))
        )

    # THEN a StorageSelected message is posted with the correct storage
    assert len(posted) == 1
    assert isinstance(posted[0], StatusView.StorageSelected)
    assert posted[0].storage is storage


# ---------------------------------------------------------------------------
# _rerender_all with storage present (NoMatches path covered in isolation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_view_rerender_all_with_storage(pilot):
    # GIVEN a StatusView populated with storage entries
    view = StatusView(id="test-rerender-storage")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            StorageInfo(
                storage_id="data/0",
                unit="mysql/0",
                kind="filesystem",
                pool="rootfs",
                location="",
                size_mib=1024,
                status="attached",
                message="",
                persistent=True,
                life="alive",
                model="dev",
                controller="ctrl",
            )
        ]
    )
    await pilot.pause()

    # WHEN _rerender_all is called
    view._rerender_all()
    await pilot.pause()

    # THEN the storage table is still displayed
    assert view.query_one("#status-storage-table").display is True


@pytest.mark.asyncio
async def test_status_view_rerender_all_storage_no_matches(pilot):
    # GIVEN a StatusView where the storage table is removed from the DOM after init
    view = StatusView(id="test-rerender-storage-nomatch")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            StorageInfo(
                storage_id="data/0",
                unit="mysql/0",
                kind="filesystem",
                pool="rootfs",
                location="",
                size_mib=1024,
                status="attached",
                message="",
                persistent=True,
                life="alive",
                model="dev",
                controller="ctrl",
            )
        ]
    )
    await pilot.pause()
    storage_table = view.query_one("#status-storage-table")
    await storage_table.remove()
    await pilot.pause()

    # WHEN _rerender_all is called while the storage widget is absent
    # THEN no exception is raised
    view._rerender_all()
    await pilot.pause()


# ---------------------------------------------------------------------------
# Clipboard with storage data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_view_format_for_clipboard_includes_storage(pilot):
    # GIVEN a StatusView with storage entries
    view = StatusView(id="test-clip-storage")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            StorageInfo(
                storage_id="data/0",
                unit="mysql/0",
                kind="filesystem",
                pool="rootfs",
                location="",
                size_mib=1024,
                status="attached",
                message="",
                persistent=True,
                life="alive",
                model="dev",
                controller="ctrl",
            )
        ]
    )
    await pilot.pause()

    # WHEN _format_for_clipboard is called
    result = view._format_for_clipboard()

    # THEN the output contains a Storage section with the storage entry
    assert "Storage" in result
    assert "mysql/0" in result


# ---------------------------------------------------------------------------
# Storage detached toggle
# ---------------------------------------------------------------------------


def _make_storage(storage_id: str, unit: str, status: str) -> StorageInfo:
    return StorageInfo(
        storage_id=storage_id,
        unit=unit,
        kind="filesystem",
        pool="rootfs",
        location="",
        size_mib=1024,
        status=status,
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )


@pytest.mark.asyncio
async def test_storage_toggle_hides_detached_by_default(pilot):
    # GIVEN a StatusView with one attached and one detached storage entry
    view = StatusView(id="test-storage-toggle-default")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            _make_storage("data/0", "mysql/0", "attached"),
            _make_storage("data/1", "mysql/1", "detached"),
        ]
    )
    await pilot.pause()

    # WHEN no toggle has been pressed (default state)
    # THEN only the attached entry is shown
    dt = view.query_one("#status-storage-table DataTable", DataTable)
    assert dt.row_count == 1
    assert view.query_one("#status-storage-table", ResourceTable).border_title is not None
    assert "Off" in str(view.query_one("#status-storage-table", ResourceTable).border_title)


@pytest.mark.asyncio
async def test_storage_toggle_shows_detached_when_enabled(pilot):
    # GIVEN a StatusView with both attached and detached entries
    view = StatusView(id="test-storage-toggle-on")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            _make_storage("data/0", "mysql/0", "attached"),
            _make_storage("data/1", "mysql/1", "detached"),
        ]
    )
    await pilot.pause()

    # WHEN the detached toggle is activated
    view.action_toggle_detached_storage()
    await pilot.pause()

    # THEN both entries are shown and the title reflects the On state
    dt = view.query_one("#status-storage-table DataTable", DataTable)
    assert dt.row_count == 2
    assert "On" in str(view.query_one("#status-storage-table", ResourceTable).border_title)


@pytest.mark.asyncio
async def test_storage_toggle_is_a_toggle(pilot):
    # GIVEN detached is turned on
    view = StatusView(id="test-storage-toggle-back")
    await _mount_view(pilot, view)
    view.update_storage(
        [
            _make_storage("data/0", "mysql/0", "attached"),
            _make_storage("data/1", "mysql/1", "detached"),
        ]
    )
    await pilot.pause()
    view.action_toggle_detached_storage()
    await pilot.pause()
    assert view.query_one("#status-storage-table DataTable", DataTable).row_count == 2

    # WHEN the toggle is pressed again
    view.action_toggle_detached_storage()
    await pilot.pause()

    # THEN detached entries are hidden again
    assert view.query_one("#status-storage-table DataTable", DataTable).row_count == 1
    assert "Off" in str(view.query_one("#status-storage-table", ResourceTable).border_title)
