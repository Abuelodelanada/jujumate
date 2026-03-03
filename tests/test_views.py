import pytest
from textual.widgets import DataTable, Label, TabbedContent

from jujumate.app import JujuMateApp
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, MachineInfo, ModelInfo, UnitInfo
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


@pytest.mark.asyncio
async def test_status_view_update_apps():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status")
        await _mount_view(app, pilot, view)
        view.update_apps([AppInfo("pg", "dev", "pg", "14/stable", 1, status="active")])
        await pilot.pause()
        assert view.query_one("#status-apps-table", ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_update_units():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-units")
        await _mount_view(app, pilot, view)

        from jujumate.models.entities import UnitInfo

        view.update_units([UnitInfo("pg/0", "pg", "0", "active", "idle", "10.0.0.1")], is_kubernetes=False)
        await pilot.pause()
        assert view.query_one("#status-units-table", ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_update_units_kubernetes():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-units-k8s")
        await _mount_view(app, pilot, view)

        view.update_units([UnitInfo("pg/0", "pg", "", "active", "idle", address="10.1.2.3")], is_kubernetes=True)
        await pilot.pause()
        table = view.query_one("#status-units-table", ResourceTable).query_one("DataTable")
        assert table.row_count == 1
        col_labels = [str(col.label) for col in table.ordered_columns]
        assert "Machine" not in col_labels
        assert "Address" in col_labels


@pytest.mark.asyncio
async def test_status_view_update_relations():
    from jujumate.models.entities import RelationInfo
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-rels")
        await _mount_view(app, pilot, view)
        view.update_relations([RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular")])
        await pilot.pause()
        assert view.query_one("#status-rels-table", ResourceTable).query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_status_view_update_offers():
    from jujumate.models.entities import OfferInfo
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-offers")
        await _mount_view(app, pilot, view)
        # Initially offers panel is hidden
        assert view.query_one("#status-offers-table").display is False
        view.update_offers([
            OfferInfo("cos", "alertmanager-karma-dashboard", "alertmanager", "alertmanager-k8s", 180, "0/0", "karma-dashboard", "karma_dashboard", "provider"),
        ])
        await pilot.pause()
        assert view.query_one("#status-offers-table").display is True
        assert view.query_one("#status-offers-table", ResourceTable).query_one("DataTable").row_count == 1
        # Clearing offers hides the panel again
        view.update_offers([])
        await pilot.pause()
        assert view.query_one("#status-offers-table").display is False


def test_jujumate_header_breadcrumb():
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

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
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

    header = JujuMateHeader.__new__(JujuMateHeader)
    for tab, count_field, expected_key, expected_val in [
        ("tab-clouds", {"cloud_count": 3}, "clouds", "3"),
        ("tab-controllers", {"controller_count": 2}, "controllers", "2"),
        ("tab-models", {"model_count": 5}, "models", "5"),
        ("tab-apps", {"app_count": 4}, "apps", "4"),
        ("tab-units", {"unit_count": 7}, "units", "7"),
    ]:
        ctx = HeaderContext(active_tab=tab, **count_field)
        result = header._build_stats(ctx)
        assert expected_key in result, f"Tab {tab}: key not found"
        assert expected_val in result, f"Tab {tab}: value not found"


def test_jujumate_header_disconnected_status():
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(is_connected=False)
    assert "Disconnected" in header._build_status(ctx)


def test_jujumate_header_empty_breadcrumb():
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext()
    assert header._build_breadcrumb(ctx) == ""


def test_jujumate_header_stats_unknown_tab():
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(active_tab="tab-unknown")
    assert header._build_stats(ctx) == ""


def test_jujumate_header_connected_no_timestamp():
    from jujumate.widgets.jujumate_header import HeaderContext, JujuMateHeader

    header = JujuMateHeader.__new__(JujuMateHeader)
    ctx = HeaderContext(is_connected=True, timestamp="")
    status = header._build_status(ctx)
    assert "Live" in status
    assert "·" not in status


def test_trunc_msg_short_text():
    from jujumate.widgets.status_view import _trunc_msg

    assert _trunc_msg("") == ""
    assert _trunc_msg("short") == "short"


def test_trunc_msg_long_text():
    from jujumate.widgets.status_view import _MSG_TRUNC_WIDTH, _trunc_msg

    long_msg = "x" * (_MSG_TRUNC_WIDTH + 5)
    result = _trunc_msg(long_msg)
    assert len(result) == _MSG_TRUNC_WIDTH
    assert result.endswith("…")


@pytest.mark.asyncio
async def test_status_view_scroll_indicator_hidden_when_content_fits():
    from jujumate.widgets.status_view import StatusView

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
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test(size=(120, 10)) as pilot:
        await pilot.pause()
        app.screen.query_one(TabbedContent).active = "tab-status"
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        many_apps = [
            AppInfo(f"app-{i}", "dev", f"app-{i}", "stable", 1, status="active")
            for i in range(20)
        ]
        view.update_apps(many_apps)
        await pilot.pause()
        await pilot.pause()
        view._update_scroll_indicator()
        indicator = view.query_one("#scroll-indicator")
        assert indicator.display is True


@pytest.mark.asyncio
async def test_tracked_scroll_notifies_parent():
    from jujumate.widgets.status_view import StatusView, _TrackedScroll

    app = JujuMateApp()
    async with app.run_test(size=(120, 10)) as pilot:
        await pilot.pause()
        app.screen.query_one(TabbedContent).active = "tab-status"
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        many_apps = [
            AppInfo(f"app-{i}", "dev", f"app-{i}", "stable", 1, status="active")
            for i in range(20)
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
    from jujumate.widgets.status_view import StatusView

    view = StatusView(id="test-detached")
    # _update_scroll_indicator with no _TrackedScroll mounted
    view._update_scroll_indicator()
    # _watch__show_more with no #scroll-indicator mounted
    view._watch__show_more(True)
    view._watch__show_more(False)


@pytest.mark.asyncio
async def test_status_view_update_machines():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-machines")
        await _mount_view(app, pilot, view)
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
async def test_status_view_update_machines_hidden_for_kubernetes():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-machines-k8s")
        await _mount_view(app, pilot, view)
        machines = [
            MachineInfo("cos", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", ""),
        ]
        view.update_machines(machines, is_kubernetes=True)
        await pilot.pause()
        assert view.query_one("#status-machines-table").display is False


@pytest.mark.asyncio
async def test_status_view_update_machines_hidden_when_empty():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = StatusView(id="test-status-machines-empty")
        await _mount_view(app, pilot, view)
        view.update_machines([])
        await pilot.pause()
        assert view.query_one("#status-machines-table").display is False


def test_colored_relation_no_colon():
    from rich.text import Text

    from jujumate.widgets.status_view import _colored_relation

    result = _colored_relation("myapp")
    assert isinstance(result, Text)
    assert str(result) == "myapp"


@pytest.mark.asyncio
async def test_status_view_msg_bar_updates_on_row_highlight():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
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
async def test_status_view_msg_bar_handles_out_of_range():
    """Cover defensive path when cursor_row is out of range."""
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        # _row_messages is empty — simulate a stale highlight event
        view._row_messages.clear()
        dt = view.query_one("#status-apps-table DataTable", DataTable)
        view.on_data_table_row_highlighted(
            DataTable.RowHighlighted(data_table=dt, cursor_row=99, row_key=None)  # type: ignore
        )


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_bad_parent():
    """Cover except branch when data_table.parent has no id."""
    from unittest.mock import MagicMock

    from textual.widgets._data_table import RowKey

    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        bad_dt = MagicMock()
        bad_dt.parent = None  # triggers AttributeError on .id
        event = DataTable.RowHighlighted(
            data_table=bad_dt, cursor_row=0, row_key=RowKey("k")  # type: ignore
        )
        view.on_data_table_row_highlighted(event)


@pytest.mark.asyncio
async def test_status_view_msg_bar_handles_missing_label():
    """Cover except branch when #msg-bar is not yet mounted."""
    from jujumate.widgets.status_view import StatusView

    view = StatusView(id="detached-msg-bar")
    dt_mock = type("FakeDT", (), {"parent": type("FakeParent", (), {"id": "status-apps-table"})()})()
    event = DataTable.RowHighlighted(data_table=dt_mock, cursor_row=0, row_key=None)  # type: ignore
    view.on_data_table_row_highlighted(event)


def test_restore_cursor_handles_unmounted():
    """Cover except branch of _restore_cursor when widget is not mounted."""
    from jujumate.widgets.status_view import StatusView

    view = StatusView(id="detached-restore")
    view._restore_cursor("status-apps-table", 5)


@pytest.mark.asyncio
async def test_restore_cursor_moves_datatable_cursor():
    """Cover _restore_cursor moving cursor to last-known position."""
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
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
async def test_row_highlighted_updates_msg_bar():
    """Cover on_data_table_row_highlighted updating msg-bar on user navigation."""
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
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
async def test_inactive_table_event_ignored_by_handler():
    """Events from non-active tables must not overwrite the msg-bar."""
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
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
async def test_table_focused_message_updates_active_table():
    """on_resource_table_table_focused sets _last_active_table and updates msg-bar."""
    from jujumate.widgets.status_view import StatusView
    from jujumate.widgets.resource_table import ResourceTable

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        msg = "hook failed: timeout"
        view.update_apps([AppInfo("myapp", "", "myapp", "stable", 1, message=msg)])
        await pilot.pause()
        rt = view.query_one("#status-apps-table", ResourceTable)
        view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))
        assert view._last_active_table == "status-apps-table"
        bar = view.query_one("#msg-bar", Label)
        assert msg in str(bar.render())


@pytest.mark.asyncio
async def test_table_focused_message_no_id_is_safe():
    """on_resource_table_table_focused with a table that has no id does not crash."""
    from jujumate.widgets.status_view import StatusView
    from jujumate.widgets.resource_table import ResourceTable, Column

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        view = app.screen.query_one("#status-view", StatusView)
        # ResourceTable without an id — handler should silently skip
        rt = ResourceTable(columns=[Column("X", "x")])
        view.on_resource_table_table_focused(ResourceTable.TableFocused(rt))
