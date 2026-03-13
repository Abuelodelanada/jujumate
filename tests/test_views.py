from unittest.mock import MagicMock, patch

import pytest
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import events
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
    _group_units,
    _TrackedScroll,
    _trunc_msg,
)
from jujumate.widgets.units_view import UnitsView


async def _mount_view(pilot, view):
    await pilot.app.screen.mount(view)
    await pilot.pause()


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
    view = view_class(id=view_id)
    await _mount_view(pilot, view)
    view.update(entities)
    assert len(view.query_one(NavigableTable)._rows) == expected_rows


@pytest.mark.asyncio
async def test_clouds_view_empty_regions_and_credentials(pilot):
    view = CloudsView(id="test-clouds")
    await _mount_view(pilot, view)
    view.update([CloudInfo("lxd", "lxd")])
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_models_view_without_region(pilot):
    view = ModelsView(id="test-models")
    await _mount_view(pilot, view)
    view.update([ModelInfo("dev", "prod", "lxd", "", "available")])
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_clouds_view_emits_cloud_selected(pilot):
    view = CloudsView(id="test-clouds")
    await _mount_view(pilot, view)
    view.update([CloudInfo("aws", "ec2"), CloudInfo("lxd", "lxd")])
    await pilot.pause()
    nt = view.query_one(NavigableTable)
    assert len(nt._rows) == 2


@pytest.mark.asyncio
async def test_controllers_view_emits_controller_selected(pilot):
    view = ControllersView(id="test-ctrl")
    await _mount_view(pilot, view)
    view.update([ControllerInfo("prod", "aws", "", "3.4.0", 2)])
    await pilot.pause()
    assert len(view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_models_view_emits_model_selected(pilot):
    view = ModelsView(id="test-models")
    await _mount_view(pilot, view)
    view.update([ModelInfo("dev", "prod", "aws", "", "available")])
    await pilot.pause()
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
    view = view_class(id=view_id)
    await _mount_view(pilot, view)
    view.update(entities)
    await pilot.pause()

    posted: list = []
    with patch.object(view, "post_message", side_effect=posted.append):
        view.on_navigable_table_row_selected(NavigableTable.RowSelected(key=row_key))

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

    view = StatusView(id=view_id)
    await _mount_view(pilot, view)
    getattr(view, update_method_name)(entities, **extra_kwargs)
    await pilot.pause()
    assert view.query_one(table_id, ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_update_units_kubernetes(pilot):

    view = StatusView(id="test-status-units-k8s")
    await _mount_view(pilot, view)

    view.update_units(
        [UnitInfo("pg/0", "pg", "", "active", "idle", address="10.1.2.3")], is_kubernetes=True
    )
    await pilot.pause()
    table = view.query_one("#status-units-table", ResourceTable).query_one("DataTable")
    assert table.row_count == 1
    col_labels = [str(col.label) for col in table.ordered_columns]
    assert "Machine" not in col_labels
    assert "Address" in col_labels


@pytest.mark.asyncio
async def test_status_view_update_offers(pilot):

    view = StatusView(id="test-status-offers")
    await _mount_view(pilot, view)
    # Initially offers panel is hidden
    assert view.query_one("#status-offers-table").display is False
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
    assert view.query_one("#status-offers-table").display is True
    assert (
        view.query_one("#status-offers-table", ResourceTable).query_one("DataTable").row_count == 1
    )
    # Clearing offers hides the panel again
    view.update_offers([])
    await pilot.pause()
    assert view.query_one("#status-offers-table").display is False


def test_jujumate_header_breadcrumb():

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
    breadcrumb = header._build_breadcrumb(ctx)
    assert "ck8s" in breadcrumb
    assert "cos" in breadcrumb

    stats = header._build_stats(ctx)
    assert "6" in stats  # app_count
    assert "3" in stats  # offer_count
    assert "4" in stats  # relation_count

    status = header._build_status(ctx)
    assert "Live" in status
    assert "14:22:03" in status


def test_jujumate_header_stats_by_tab():

    header = JujuMateHeader.__new__(JujuMateHeader)
    for tab, count_field, expected_key, expected_val in [
        ("tab-clouds", {"cloud_count": 3}, "clouds", "3"),
        ("tab-controllers", {"controller_count": 2}, "controllers", "2"),
        ("tab-models", {"model_count": 5}, "models", "5"),
    ]:
        ctx = HeaderContext(active_tab=tab, **count_field)
        result = header._build_stats(ctx)
        assert expected_key in result, f"Tab {tab}: key not found"
        assert expected_val in result, f"Tab {tab}: value not found"


def test_jujumate_header_disconnected_status():

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(is_connected=False)
    assert "Disconnected" in header._build_status(ctx)


def test_jujumate_header_empty_breadcrumb():

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext()
    assert header._build_breadcrumb(ctx) == ""


def test_jujumate_header_stats_unknown_tab():

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(active_tab="tab-unknown")
    assert header._build_stats(ctx) == ""


def test_jujumate_header_connected_no_timestamp():

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(is_connected=True, timestamp="")
    status = header._build_status(ctx)
    assert "Live" in status
    assert "·" not in status


@pytest.mark.parametrize(
    "text,expected,check_truncated",
    [
        pytest.param("", "", False, id="empty"),
        pytest.param("short", "short", False, id="short"),
        pytest.param("x" * (_MSG_TRUNC_WIDTH + 5), None, True, id="long"),
    ],
)
def test_trunc_msg(text, expected, check_truncated):

    result = _trunc_msg(text)
    if check_truncated:
        assert len(result) == _MSG_TRUNC_WIDTH
        assert result.endswith("…")
    else:
        assert result == expected


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_hidden_when_content_fits():

    app = JujuMateApp()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")])
        await pilot.pause()
        view._update_scroll_indicator()
        indicator = view.query_one("#scroll-indicator")
        assert indicator.display is False


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_shown_when_content_overflows():

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
        view._update_scroll_indicator()
        indicator = view.query_one("#scroll-indicator")
        assert indicator.display is True


@pytest.mark.asyncio
async def test_tracked_scroll_notifies_parent():

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
        vs = view.query_one(_TrackedScroll)
        vs.watch_scroll_y(0.0)
        await pilot.pause()


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_handles_missing_widgets():
    """Cover defensive except branches when widgets aren't mounted."""

    view = StatusView(id="test-detached")
    # _update_scroll_indicator with no _TrackedScroll mounted
    view._update_scroll_indicator()
    # _watch__show_more with no #scroll-indicator mounted
    view._watch__show_more(True)
    view._watch__show_more(False)


@pytest.mark.asyncio
async def test_status_view_update_machines(pilot):

    view = StatusView(id="test-status-machines")
    await _mount_view(pilot, view)
    machines = [
        MachineInfo("dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a"),
        MachineInfo("dev", "1", "started", "10.0.0.2", "i-5678", "ubuntu@22.04", "us-east-1b"),
    ]
    view.update_machines(machines)
    await pilot.pause()
    table = view.query_one("#status-machines-table", ResourceTable)
    assert table.query_one("DataTable").row_count == 2
    assert view.query_one("#status-machines-table").display is True


@pytest.mark.asyncio
async def test_status_view_update_machines_hidden_for_kubernetes(pilot):

    view = StatusView(id="test-status-machines-k8s")
    await _mount_view(pilot, view)
    machines = [
        MachineInfo("cos", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", ""),
    ]
    view.update_machines(machines, is_kubernetes=True)
    await pilot.pause()
    assert view.query_one("#status-machines-table").display is False


@pytest.mark.asyncio
async def test_status_view_update_machines_hidden_when_empty(pilot):

    view = StatusView(id="test-status-machines-empty")
    await _mount_view(pilot, view)
    view.update_machines([])
    await pilot.pause()
    assert view.query_one("#status-machines-table").display is False


def test_colored_relation_no_colon():

    result = _colored_relation("myapp")
    assert isinstance(result, Text)
    assert str(result) == "myapp"


@pytest.mark.asyncio
async def test_status_view_msg_bar_updates_on_row_highlight(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    long_msg = "unit is waiting for something to happen"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=long_msg)])
    await pilot.pause()
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    view._last_active_table = "status-apps-table"
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )
    bar = view.query_one("#msg-bar", Label)
    assert long_msg in str(bar.render())


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_out_of_range(pilot):
    """Cover defensive path when cursor_row is out of range."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    # _row_messages is empty — simulate a stale highlight event
    view._row_messages.clear()
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=99, row_key=None)  # type: ignore
    )


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_bad_parent(pilot):
    """Cover except branch when data_table.parent has no id."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    bad_dt = MagicMock()
    bad_dt.parent = None  # triggers AttributeError on .id
    event = DataTable.RowHighlighted(
        data_table=bad_dt,
        cursor_row=0,
        row_key=RowKey("k"),  # type: ignore
    )
    view.on_data_table_row_highlighted(event)


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_missing_label():
    """Cover except branch when #msg-bar is not yet mounted."""

    view = StatusView(id="detached-msg-bar")
    dt_mock = type(
        "FakeDT", (), {"parent": type("FakeParent", (), {"id": "status-apps-table"})()}
    )()
    event = DataTable.RowHighlighted(data_table=dt_mock, cursor_row=0, row_key=None)  # type: ignore
    view.on_data_table_row_highlighted(event)


def test_restore_cursor_handles_unmounted():
    """Cover except branch of _restore_cursor when widget is not mounted."""

    view = StatusView(id="detached-restore")
    view._restore_cursor("status-apps-table", 5)


@pytest.mark.asyncio
async def test_restore_cursor_moves_datatable_cursor(pilot):
    """Cover _restore_cursor moving cursor to last-known position."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    msgs = ["msg0", "msg1", "msg2"]
    apps = [AppInfo(f"app{i}", "", f"app{i}", "stable", 1, message=msgs[i]) for i in range(3)]
    view.update_apps(apps)
    await pilot.pause()
    view._last_cursor["status-apps-table"] = 2
    view._restore_cursor("status-apps-table", 3)
    await pilot.pause()
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    assert dt.cursor_row == 2


@pytest.mark.asyncio
async def test_row_highlighted_updates_msg_bar(pilot):
    """Cover on_data_table_row_highlighted updating msg-bar on user navigation."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    msg = "hook failed: unit not ready"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=msg)])
    await pilot.pause()
    # Simulate user having previously navigated to the apps table
    dt = view.query_one("#status-apps-table DataTable", DataTable)
    view._last_active_table = "status-apps-table"
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )
    bar = view.query_one("#msg-bar", Label)
    assert msg in str(bar.render())


@pytest.mark.asyncio
async def test_inactive_table_event_ignored_by_handler(pilot):
    """Events from non-active tables must not overwrite the msg-bar."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    apps = [AppInfo("myapp", "", "myapp", "stable", 1, message="hook failed")]
    machines = [MachineInfo("m", "0", "running", "", "", "", "", message="running")]
    view.update_apps(apps)
    view.update_machines(machines)
    await pilot.pause()
    bar = view.query_one("#msg-bar", Label)
    bar.update("sentinel")
    # Simulate refresh event from machines table while user is on apps table
    view._last_active_table = "status-apps-table"
    dt = view.query_one("#status-machines-table DataTable", DataTable)
    view.on_data_table_row_highlighted(
        DataTable.RowHighlighted(data_table=dt, cursor_row=0, row_key=None)  # type: ignore
    )
    # msg-bar must not be overwritten by the machines event
    assert "sentinel" in str(bar.render())


@pytest.mark.asyncio
async def test_table_focused_message_updates_active_table(pilot):
    """on_resource_table_table_focused sets _last_active_table and updates msg-bar."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    msg = "hook failed: timeout"
    view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=msg)])
    await pilot.pause()
    rt = view.query_one("#status-apps-table", ResourceTable)
    view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))
    assert view._last_active_table == "status-apps-table"
    bar = view.query_one("#msg-bar", Label)
    assert msg in str(bar.render())


@pytest.mark.asyncio
async def test_table_focused_message_no_id_is_safe(pilot):
    """on_resource_table_table_focused with a table that has no id does not crash."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    # ResourceTable without an id — handler should silently skip
    rt = ResourceTable(columns=[Column("X", "x")])
    view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))


# ─────────────────────────────────────────────────────────────────────────────
# AppsView
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apps_view_update(pilot):

    view = AppsView(id="test-apps")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update(
        [
            AppInfo("pg", "dev", "postgresql", "14/stable", 363, unit_count=1, status="active"),
            AppInfo("mysql", "dev", "mysql", "8/stable", 100, unit_count=2, status="blocked"),
        ]
    )
    await pilot.pause()
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == 2


@pytest.mark.asyncio
async def test_apps_view_empty(pilot):

    view = AppsView(id="test-apps-empty")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([])
    await pilot.pause()
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == 0


@pytest.mark.asyncio
async def test_apps_view_row_selection_posts_app_selected(pilot):

    view = AppsView(id="test-apps-sel")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([AppInfo("pg", "dev", "postgresql", "14/stable", 363)])
    await pilot.pause()
    posted: list = []
    with patch.object(view, "post_message", side_effect=posted.append):
        dt = view.query_one(ResourceTable).query_one("DataTable")
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("dev/pg"))
        )
    assert len(posted) == 1
    assert isinstance(posted[0], AppsView.AppSelected)
    assert posted[0].name == "dev/pg"


@pytest.mark.asyncio
async def test_apps_view_row_selection_ignores_none_key(pilot):

    view = AppsView(id="test-apps-none")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([AppInfo("pg", "dev", "postgresql", "14/stable", 363)])
    await pilot.pause()
    posted: list = []
    with patch.object(view, "post_message", side_effect=posted.append):
        dt = view.query_one(ResourceTable).query_one("DataTable")
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey(None))
        )
    assert posted == []


# ─────────────────────────────────────────────────────────────────────────────
# UnitsView
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_units_view_update(pilot):

    view = UnitsView(id="test-units")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update(
        [
            UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1"),
            UnitInfo("pg/1", "pg", "1", "active", "idle", "10.0.0.2"),
        ]
    )
    await pilot.pause()
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == 2


@pytest.mark.asyncio
async def test_units_view_empty(pilot):

    view = UnitsView(id="test-units-empty")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update([])
    await pilot.pause()
    assert view.query_one(ResourceTable).query_one("DataTable").row_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# NavigableTable — cursor navigation & Enter key
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_navigable_table_cursor_navigation(pilot):

    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-nav")
    await pilot.app.screen.mount(nt)
    await pilot.pause()
    nt.update_rows([("row0",), ("row1",), ("row2",)], keys=["k0", "k1", "k2"])
    await pilot.pause()

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
    assert nt._cursor == 0


@pytest.mark.asyncio
async def test_navigable_table_enter_posts_row_selected(pilot):

    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-enter")
    await pilot.app.screen.mount(nt)
    await pilot.pause()
    nt.update_rows([("row0",), ("row1",)], keys=["key0", "key1"])
    nt._cursor = 1

    posted: list = []
    with patch.object(nt, "post_message", side_effect=posted.append):
        nt.on_key(events.Key(key="enter", character="\r"))

    assert len(posted) == 1
    assert isinstance(posted[0], NavigableTable.RowSelected)
    assert posted[0].key == "key1"


@pytest.mark.asyncio
async def test_navigable_table_enter_no_rows_does_nothing(pilot):

    nt = NavigableTable(columns=[Column("Name", "name")], id="test-nt-norow")
    await pilot.app.screen.mount(nt)

    posted: list = []
    with patch.object(nt, "post_message", side_effect=posted.append):
        nt.on_key(events.Key(key="enter", character="\r"))
    assert posted == []


# ─────────────────────────────────────────────────────────────────────────────
# StatusView — filter, row selection, messages, saas
# ─────────────────────────────────────────────────────────────────────────────


def test_group_units_with_orphan_subordinates():

    principal = UnitInfo("pg/0", "pg", "0", "active", "idle")
    sub_known = UnitInfo("nrpe/0", "nrpe", "0", "active", "idle", subordinate_of="pg/0")
    sub_orphan = UnitInfo("lldp/0", "lldp", "0", "active", "idle", subordinate_of="missing/0")
    result = _group_units([principal, sub_known, sub_orphan])
    assert result[0] == (principal, "")
    assert result[1] == (sub_known, "└─ ")
    assert result[2] == (sub_orphan, "└─ ")


def test_status_view_relation_selected_message():

    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")
    assert StatusView.RelationSelected(rel).relation is rel


def test_status_view_app_selected_message():

    ai = AppInfo("pg", "dev", "pg", "14/stable", 1)
    assert StatusView.AppSelected(ai).app is ai


@pytest.mark.asyncio
async def test_status_view_update_saas_shown(pilot):

    view = StatusView(id="test-saas-show")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update_saas([SAASInfo("dev", "remote-pg", "active", "my-store", "my-store:admin/pg")])
    await pilot.pause()
    assert view.query_one("#status-saas-table").display is True


@pytest.mark.asyncio
async def test_status_view_update_saas_hidden_when_empty(pilot):

    view = StatusView(id="test-saas-empty")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    view.update_saas([])
    await pilot.pause()
    assert view.query_one("#status-saas-table").display is False


@pytest.mark.asyncio
async def test_status_view_filter_activate_and_close(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    bar = view.query_one("#filter-bar")
    assert "visible" not in bar.classes

    view.action_activate_filter()
    await pilot.pause()
    assert "visible" in bar.classes

    view._filter = "pg"
    view.action_close_filter()
    await pilot.pause()
    assert "visible" not in bar.classes
    assert view._filter == ""


@pytest.mark.asyncio
async def test_status_view_filter_filters_apps(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps(
        [
            AppInfo("postgresql", "dev", "postgresql", "14/stable", 1, status="active"),
            AppInfo("wordpress", "dev", "wordpress", "stable", 1, status="active"),
        ]
    )
    await pilot.pause()
    assert view.query_one("#status-apps-table DataTable").row_count == 2
    view._filter = "postgres"
    view._rerender_all()
    await pilot.pause()
    assert view.query_one("#status-apps-table DataTable").row_count == 1
    view._filter = ""
    view._rerender_all()
    await pilot.pause()
    assert view.query_one("#status-apps-table DataTable").row_count == 2


@pytest.mark.asyncio
async def test_status_view_filter_filters_relations(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_relations(
        [
            RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular"),
            RelationInfo("dev", "mysql:db", "wp:db", "mysql", "regular"),
        ]
    )
    await pilot.pause()
    view._filter = "mysql"
    view._render_relations()
    await pilot.pause()
    assert view.query_one("#status-rels-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_row_selected_posts_app_selected(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1)])
    await pilot.pause()
    posted: list = []
    with patch.object(view, "post_message", side_effect=posted.append):
        dt = view.query_one("#status-apps-table DataTable", DataTable)
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("k"))
        )
    assert len(posted) == 1
    assert isinstance(posted[0], StatusView.AppSelected)
    assert posted[0].app.name == "pg"


@pytest.mark.asyncio
async def test_status_view_row_selected_posts_relation_selected(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_relations([RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")])
    await pilot.pause()
    posted: list = []
    with patch.object(view, "post_message", side_effect=posted.append):
        dt = view.query_one("#status-rels-table DataTable", DataTable)
        view.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("k"))
        )
    assert len(posted) == 1
    assert isinstance(posted[0], StatusView.RelationSelected)
    assert posted[0].relation.interface == "pgsql"


@pytest.mark.asyncio
async def test_status_view_check_action_close_filter(pilot):

    view = pilot.app.screen.query_one("#status-view", StatusView)
    bar = view.query_one("#filter-bar")

    bar.remove_class("visible")
    view._filter = ""
    assert view.check_action("close_filter", ()) is False

    bar.add_class("visible")
    assert view.check_action("close_filter", ()) is True

    bar.remove_class("visible")
    view._filter = "pg"
    assert view.check_action("close_filter", ()) is True

    assert view.check_action("activate_filter", ()) is True


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

    result = _ac_format_plain_text(ai, entries)
    for fragment in expected_fragments:
        assert fragment in result


@pytest.mark.asyncio
async def test_app_config_view_update(pilot):

    view = AppConfigView(id="test-ac")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    view.update(ai, entries)
    await pilot.pause()
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

    view = AppConfigView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()
    getattr(view, method_name)(*method_args)
    await pilot.pause()
    assert view.query_one("#ac-empty").display is True
    assert view.query_one("#ac-panel").display is False


# ─────────────────────────────────────────────────────────────────────────────
# RelationDataView — pure helpers + mounted widget
# ─────────────────────────────────────────────────────────────────────────────


def test_kv_table_with_data():

    assert _kv_table({"key1": "value1", "key2": "value2"}).row_count == 2


def test_kv_table_empty():

    assert _kv_table({}).row_count == 1  # <empty> row


def test_unit_panel_with_leader():

    assert isinstance(_unit_panel("pg/0", {"key": "val"}, is_leader=True, color="#77216F"), Panel)


def test_unit_panel_non_leader():

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

    result = _rd_format_plain_text(rel, entries)
    for fragment in expected_fragments:
        assert fragment in result


@pytest.mark.asyncio
async def test_relation_data_view_update(pilot):

    view = RelationDataView(id="test-rd")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    view.update(rel, [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")])
    await pilot.pause()
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

    view = RelationDataView(id=view_id)
    await pilot.app.screen.mount(view)
    await pilot.pause()
    getattr(view, method_name)(*method_args)
    await pilot.pause()
    assert view.query_one("#rd-empty").display is True
    assert view.query_one("#rd-panel").display is False


# ─────────────────────────────────────────────────────────────────────────────
# StatusView — coverage of previously uncovered branches
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_row_highlighted_has_focus_sets_active_table(pilot):
    """Line 454: has_focus=True branch sets _last_active_table."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1)])
    await pilot.pause()

    mock_event = MagicMock()
    mock_event.data_table.has_focus = True
    mock_event.data_table.parent.id = "status-apps-table"
    mock_event.cursor_row = 0
    view.on_data_table_row_highlighted(mock_event)

    assert view._last_active_table == "status-apps-table"


@pytest.mark.asyncio
async def test_status_view_resource_table_focused_exception_safe(pilot):
    """Lines 480-481: exception in on_resource_table_table_focused is silently swallowed."""

    view = pilot.app.screen.query_one("#status-view", StatusView)

    broken_event = MagicMock()
    broken_event.resource_table.id = "status-apps-table"
    broken_event.resource_table.query_one = MagicMock(side_effect=RuntimeError("broken"))
    view.on_resource_table_table_focused(broken_event)  # must not raise


@pytest.mark.asyncio
async def test_status_view_row_selected_exception_safe(pilot):
    """Lines 530-531: exception in on_data_table_row_selected is silently swallowed."""

    view = pilot.app.screen.query_one("#status-view", StatusView)

    class _BadEvent:
        @property
        def data_table(self):
            raise RuntimeError("bad table")

    view.on_data_table_row_selected(_BadEvent())  # must not raise


@pytest.mark.asyncio
async def test_status_view_rerender_all_exception_safe(pilot):
    """Lines 537-558: all six render methods raise — _rerender_all swallows each."""

    view = pilot.app.screen.query_one("#status-view", StatusView)

    with (
        patch.object(view, "_render_apps", side_effect=Exception),
        patch.object(view, "_render_saas", side_effect=Exception),
        patch.object(view, "_render_units", side_effect=Exception),
        patch.object(view, "_render_offers", side_effect=Exception),
        patch.object(view, "_render_machines", side_effect=Exception),
        patch.object(view, "_render_relations", side_effect=Exception),
    ):
        view._rerender_all()  # must not raise


@pytest.mark.asyncio
async def test_status_view_check_action_close_filter_exception_safe(pilot):
    """Lines 565-566: query_one raises in check_action → returns False."""

    view = pilot.app.screen.query_one("#status-view", StatusView)

    with patch.object(view, "query_one", side_effect=Exception("no widget")):
        result = view.check_action("close_filter", ())

    assert result is False


@pytest.mark.asyncio
async def test_status_view_filter_changed_updates_filter(pilot):
    """Lines 583-584: Input.Changed on #filter-input sets _filter and rerenders."""

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

    fi = view.query_one("#filter-input", Input)
    view._on_filter_changed(Input.Changed(input=fi, value="postgres"))
    await pilot.pause()

    assert view._filter == "postgres"
    assert view.query_one("#status-apps-table DataTable", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_status_view_filter_submitted_hides_input(pilot):
    """Input.Submitted on #filter-input hides the filter bar."""

    view = pilot.app.screen.query_one("#status-view", StatusView)
    view.action_activate_filter()
    await pilot.pause()

    bar = view.query_one("#filter-bar")
    assert "visible" in bar.classes

    fi = view.query_one("#filter-input", Input)
    view._on_filter_submitted(Input.Submitted(input=fi, value="pg"))
    await pilot.pause()

    assert "visible" not in bar.classes
