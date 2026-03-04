from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import DataTable, TabbedContent
from textual.widgets._data_table import RowKey

from jujumate.app import JujuMateApp
from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    ControllersUpdated,
    DataRefreshed,
    JujuPoller,
    MachinesUpdated,
    ModelsUpdated,
    OffersUpdated,
    RelationsUpdated,
    UnitsUpdated,
)
from jujumate.config import JujuConfig, JujuConfigError
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
    SecretInfo,
    UnitInfo,
)
from jujumate.settings import AppSettings
from jujumate.widgets.navigable_table import NavigableTable


@pytest.mark.asyncio
async def test_app_mounts_main_screen(pilot):
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_default_tab_is_clouds(pilot):
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-clouds"


@pytest.mark.asyncio
async def test_keybinding_m_switches_to_models(pilot):
    await pilot.press("m")
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"


@pytest.mark.asyncio
async def test_keybinding_s_switches_to_status(pilot):
    await pilot.press("s")
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-status"


@pytest.mark.asyncio
async def test_keybinding_q_exits(pilot):
    await pilot.press("q")
    assert pilot.app.return_value is None


@pytest.mark.asyncio
async def test_keybinding_r_triggers_refresh(pilot):
    await pilot.press("r")
    await pilot.pause()
    # action_refresh_data calls notify() — verify app is still running
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_app_falls_back_when_theme_not_found():
    settings = AppSettings(theme="nonexistent-theme")
    app = JujuMateApp(settings=settings)
    async with app.run_test() as pilot:
        await pilot.pause()
        # App should still mount correctly despite unknown theme
        assert app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_message_handlers_update_views(pilot):
    screen = pilot.app.screen

    screen.on_clouds_updated(CloudsUpdated(clouds=[CloudInfo("aws", "ec2")]))
    screen.on_controllers_updated(
        ControllersUpdated(
            controllers=[ControllerInfo("ctrl", "aws", "", "3.4.0", model_count=1)]
        )
    )
    screen.on_models_updated(
        ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")])
    )
    screen.on_apps_updated(AppsUpdated(apps=[AppInfo("pg", "dev", "pg", "14/stable", 1)]))
    screen.on_units_updated(UnitsUpdated(units=[UnitInfo("pg/0", "pg", "0", "active", "idle")]))
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))

    await pilot.pause()
    assert screen._is_connected is True
    assert screen._last_refresh_ts == "12:00:00"


@pytest.mark.asyncio
async def test_connection_failed_sets_subtitle(pilot):
    pilot.app.screen.on_connection_failed(ConnectionFailed(error="timeout"))
    assert pilot.app.screen._is_connected is False


@pytest.mark.asyncio
async def test_action_refresh_data_without_poller(pilot):
    # _poller is None at this point — should not crash
    await pilot.app.screen.action_refresh_data()
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_refresh_header_before_mount_does_not_crash():
    """_refresh_header guard: calling before widgets are mounted must not raise."""
    from jujumate.screens.main_screen import MainScreen
    from jujumate.settings import AppSettings
    from pathlib import Path

    screen = MainScreen(settings=AppSettings(juju_data_dir=Path("/nonexistent")))
    # Calling without a mounted app should silently return (guard path)
    screen._refresh_header()  # must not raise


@pytest.mark.asyncio
async def test_connect_and_poll_connection_failure(pilot):
    screen = pilot.app.screen
    with patch(
        "jujumate.screens.main_screen.load_config",
        side_effect=JujuConfigError("no config"),
    ):
        await screen._connect_and_poll()
    await pilot.pause()
    assert screen._is_connected is False


@pytest.mark.asyncio
async def test_connect_and_poll_success(pilot):
    screen = pilot.app.screen
    with (
        patch(
            "jujumate.screens.main_screen.load_config",
            return_value=JujuConfig(current_controller="prod", controllers=["prod"]),
        ),
        patch("jujumate.screens.main_screen.JujuPoller") as MockPoller,
    ):
        mock_poller = AsyncMock()
        MockPoller.return_value = mock_poller
        await screen._connect_and_poll()
        MockPoller.assert_called_once_with(controller_names=["prod"], target=screen)
        mock_poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_and_poll_sets_auto_select_from_config(pilot):
    screen = pilot.app.screen
    with (
        patch(
            "jujumate.screens.main_screen.load_config",
            return_value=JujuConfig(
                current_controller="prod", controllers=["prod"], current_model="mymodel"
            ),
        ),
        patch("jujumate.screens.main_screen.JujuPoller") as MockPoller,
    ):
        mock_poller = AsyncMock()
        MockPoller.return_value = mock_poller
        await screen._connect_and_poll()
        assert screen._auto_select_model == "mymodel"


@pytest.mark.asyncio
async def test_action_refresh_data_with_poller(pilot):
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    await screen.action_refresh_data()
    screen._poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_selected_switches_to_controllers_and_filters(pilot):
    from jujumate.widgets.clouds_view import CloudsView
    from jujumate.widgets.controllers_view import ControllersView

    screen = pilot.app.screen
    # Populate data
    screen._all_controllers = [
        ControllerInfo("prod", "aws", "", "3.4.0", 1),
        ControllerInfo("dev", "lxd", "", "3.4.0", 1),
    ]
    # Simulate cloud selection
    screen.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # Should switch to controllers tab
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-controllers"
    # Should only show aws controller
    ctrl_view = screen.query_one("#controllers-view", ControllersView)
    assert len(ctrl_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_controller_selected_switches_to_models_and_filters(pilot):
    from jujumate.widgets.controllers_view import ControllersView
    from jujumate.widgets.models_view import ModelsView

    screen = pilot.app.screen
    screen._all_models = [
        ModelInfo("dev", "prod", "aws", "", "available"),
        ModelInfo("staging", "other-ctrl", "aws", "", "available"),
    ]
    screen.on_controllers_view_controller_selected(
        ControllersView.ControllerSelected(name="prod")
    )
    await pilot.pause()
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"
    models_view = screen.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_model_selected_switches_to_status_and_filters(pilot):
    from jujumate.widgets.models_view import ModelsView
    from jujumate.widgets.status_view import StatusView

    screen = pilot.app.screen
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1),
        AppInfo("mysql", "prod", "mysql", "8/stable", 1),
    ]
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get_status_details = AsyncMock(return_value=([], [], []))
    with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
        screen._selected_controller = "ctrl"
        screen.on_models_view_model_selected(ModelsView.ModelSelected(name="ctrl/dev"))
        await pilot.pause()
        await pilot.pause()
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-status"
    # Status view shows apps for selected model
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-apps-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_clear_filter_resets_all_selections(pilot):
    from jujumate.widgets.controllers_view import ControllersView

    screen = pilot.app.screen
    screen._selected_cloud = "aws"
    screen._selected_controller = "prod"
    screen._all_controllers = [
        ControllerInfo("prod", "aws", "", "3.4.0", 1),
        ControllerInfo("dev", "lxd", "", "3.4.0", 1),
    ]
    screen.action_clear_filter()
    await pilot.pause()
    assert screen._selected_cloud is None
    assert screen._selected_controller is None
    # Both controllers should show now
    ctrl_view = screen.query_one("#controllers-view", ControllersView)
    assert len(ctrl_view.query_one(NavigableTable)._rows) == 2


def test_asyncio_exception_handler_suppresses_closed_errors():
    from unittest.mock import MagicMock

    from jujumate.app import _asyncio_exception_handler

    loop = MagicMock()
    # Should suppress RuntimeError("Event loop is closed")
    _asyncio_exception_handler(loop, {"exception": RuntimeError("Event loop is closed")})
    loop.default_exception_handler.assert_not_called()

    # Should suppress OSError("Bad file descriptor")
    _asyncio_exception_handler(loop, {"exception": OSError("Bad file descriptor")})
    loop.default_exception_handler.assert_not_called()

    # Should suppress RuntimeError("cannot reuse already awaited coroutine")
    _asyncio_exception_handler(loop, {"exception": RuntimeError("cannot reuse already awaited coroutine")})
    loop.default_exception_handler.assert_not_called()

    # Should suppress "task was destroyed but it is pending" message
    _asyncio_exception_handler(loop, {"message": "Task was destroyed but it is pending!"})
    loop.default_exception_handler.assert_not_called()


def test_asyncio_exception_handler_forwards_other_errors():
    from unittest.mock import MagicMock

    from jujumate.app import _asyncio_exception_handler

    loop = MagicMock()
    ctx = {"exception": ValueError("something unexpected")}
    _asyncio_exception_handler(loop, ctx)
    loop.default_exception_handler.assert_called_once_with(ctx)


def test_asyncio_exception_handler_forwards_non_exception_context():
    from unittest.mock import MagicMock

    from jujumate.app import _asyncio_exception_handler

    loop = MagicMock()
    ctx = {"message": "some asyncio message"}
    _asyncio_exception_handler(loop, ctx)
    loop.default_exception_handler.assert_called_once_with(ctx)


@pytest.mark.asyncio
async def test_relations_updated_populates_status_view(pilot):
    from jujumate.widgets.status_view import StatusView

    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen.on_relations_updated(
        RelationsUpdated(
            model="dev",
            relations=[
                RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular"),
            ],
        )
    )
    await pilot.pause()
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-rels-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_relations_updated_replaces_existing_for_same_model(pilot):
    screen = pilot.app.screen
    screen._all_relations = [
        RelationInfo("dev", "a:x", "b:x", "iface", "regular"),
        RelationInfo("prod", "c:x", "d:x", "iface2", "regular"),
    ]
    screen._selected_model = "dev"
    screen.on_relations_updated(
        RelationsUpdated(
            model="dev",
            relations=[RelationInfo("dev", "new:x", "new2:x", "iface3", "regular")],
        )
    )
    await pilot.pause()
    dev_rels = [r for r in screen._all_relations if r.model == "dev"]
    prod_rels = [r for r in screen._all_relations if r.model == "prod"]
    assert len(dev_rels) == 1
    assert dev_rels[0].provider == "new:x"
    assert len(prod_rels) == 1  # prod untouched


@pytest.mark.asyncio
async def test_offers_updated_populates_status_view(pilot):
    from jujumate.widgets.status_view import StatusView

    screen = pilot.app.screen
    screen._selected_model = "cos"
    screen.on_offers_updated(
        OffersUpdated(
            model="cos",
            offers=[
                OfferInfo("cos", "alertmanager-karma-dashboard", "alertmanager", "alertmanager-k8s", 180, "0/0", "karma-dashboard", "karma_dashboard", "provider"),
            ],
        )
    )
    await pilot.pause()
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-offers-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_machines_updated_populates_status_view(pilot):
    from jujumate.widgets.status_view import StatusView

    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen._all_models = [ModelInfo("dev", "prod", "aws", "us-east-1", "available")]
    screen.on_machines_updated(
        MachinesUpdated(
            machines=[
                MachineInfo("dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a"),
            ],
        )
    )
    await pilot.pause()
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-machines-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_fetch_relations_worker_posts_message(pilot):
    from jujumate.models.entities import RelationInfo

    screen = pilot.app.screen
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get_status_details = AsyncMock(return_value=([rel], [], []))
    with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
        screen._fetch_relations("ctrl", "dev")
        await pilot.pause()
        await pilot.pause()
    assert any(r.model == "dev" for r in screen._all_relations)


@pytest.mark.asyncio
async def test_fetch_relations_worker_handles_exception(pilot):
    screen = pilot.app.screen
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("boom"))
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
        screen._fetch_relations("ctrl", "dev")
        await pilot.pause()
        await pilot.pause()
    # Empty RelationsUpdated was posted — no relations for "dev"
    dev_rels = [r for r in screen._all_relations if r.model == "dev"]
    assert dev_rels == []


@pytest.mark.asyncio
async def test_auto_select_navigates_to_status_on_first_refresh(pilot):
    screen = pilot.app.screen
    screen._auto_select_model = "dev"
    screen.on_models_updated(
        ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")])
    )
    screen.on_apps_updated(AppsUpdated(apps=[AppInfo("pg", "dev", "pg", "14/stable", 1)]))
    screen.on_units_updated(UnitsUpdated(units=[UnitInfo("pg/0", "pg", "0", "active", "idle")]))
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))
    await pilot.pause()
    assert screen._selected_model == "dev"
    assert screen._selected_controller == "ctrl"
    assert screen.query_one(TabbedContent).active == "tab-status"
    # auto_select cleared after first use
    assert screen._auto_select_model is None


@pytest.mark.asyncio
async def test_auto_select_not_found_does_not_crash(pilot):
    screen = pilot.app.screen
    screen._auto_select_model = "nonexistent"
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))
    await pilot.pause()
    assert screen._selected_model is None
    assert screen._auto_select_model is None


@pytest.mark.asyncio
async def test_help_screen_opens_and_closes_with_question_mark(pilot):
    assert pilot.app.screen.__class__.__name__ == "MainScreen"
    await pilot.press("question_mark")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("question_mark")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_help_screen_closes_with_escape(pilot):
    await pilot.press("question_mark")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("escape")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


# ─────────────────────────────────────────────────────────────────────────────
# SecretsScreen & SecretDetailScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secrets_screen_populate_with_secrets(pilot):
    from jujumate.screens.secrets_screen import SecretsScreen

    secrets = [
        SecretInfo(uri="csec:abc123", label="my-secret", owner="dev",
                   description="", revision=1, rotate_policy="", created="2024-01-01", updated="2024-01-01"),
        SecretInfo(uri="csec:def456", label="other", owner="dev",
                   description="", revision=2, rotate_policy="", created="2024-01-02", updated="2024-01-02"),
    ]
    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate(secrets)
        await pilot.pause()
    dt = screen.query_one(DataTable)
    assert dt.row_count == 2


@pytest.mark.asyncio
async def test_secrets_screen_populate_empty(pilot):
    from jujumate.screens.secrets_screen import SecretsScreen

    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([])
        await pilot.pause()
    dt = screen.query_one(DataTable)
    assert dt.row_count == 0


@pytest.mark.asyncio
async def test_secrets_screen_show_error(pilot):
    from jujumate.screens.secrets_screen import SecretsScreen

    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._show_error("connection refused")
        await pilot.pause()
    # _show_error updates #secrets-loading label to show error text
    loading = screen.query_one("#secrets-loading")
    assert loading.display is True


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_pushes_detail(pilot):
    from jujumate.screens.secrets_screen import SecretDetailScreen, SecretsScreen

    secrets = [SecretInfo(uri="csec:abc", label="my-secret", owner="dev",
                          description="", revision=1, rotate_policy="", created="2024-01-01", updated="2024-01-01")]
    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate(secrets)
        await pilot.pause()
    dt = screen.query_one(DataTable)
    screen.on_data_table_row_selected(
        DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
    )
    await pilot.pause()
    assert isinstance(pilot.app.screen, SecretDetailScreen)


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_out_of_range_safe(pilot):
    from jujumate.screens.secrets_screen import SecretsScreen

    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([])
        await pilot.pause()
    dt = screen.query_one(DataTable)
    # Should not raise even when index is out of range (row_key "99" > 0 secrets)
    screen.on_data_table_row_selected(
        DataTable.RowSelected(data_table=dt, cursor_row=99, row_key=RowKey("99"))
    )
    await pilot.pause()


@pytest.mark.asyncio
async def test_secret_detail_screen_shows_fields(pilot):
    from textual.widgets import Label

    from jujumate.screens.secrets_screen import SecretDetailScreen

    secret = SecretInfo(uri="csec:abc123", label="my-secret", owner="dev",
                        description="A test secret", revision=1, rotate_policy="",
                        created="2024-01-01T00:00:00", updated="2024-01-01T00:00:00")
    screen = SecretDetailScreen(secret)
    await pilot.app.push_screen(screen)
    await pilot.pause()
    labels = screen.query(Label)
    all_text = "\n".join(str(lbl.render()) for lbl in labels)
    assert "csec:abc123" in all_text
    assert "my-secret" in all_text


# ─────────────────────────────────────────────────────────────────────────────
# AppConfigScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_config_screen_success(pilot):
    from jujumate.screens.app_config_screen import AppConfigScreen
    from jujumate.widgets.app_config_view import AppConfigView

    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]

    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(AppConfigView).update(ai, entries)
        await pilot.pause()
    view = screen.query_one(AppConfigView)
    assert view.query_one("#ac-scroll").display is True


@pytest.mark.asyncio
async def test_app_config_screen_fetch_error(pilot):
    from jujumate.screens.app_config_screen import AppConfigScreen
    from jujumate.widgets.app_config_view import AppConfigView

    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")

    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(AppConfigView).show_error(ai, "timeout")
        await pilot.pause()
    view = screen.query_one(AppConfigView)
    assert view.query_one("#ac-empty").display is True


# ─────────────────────────────────────────────────────────────────────────────
# RelationDataScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_relation_data_screen_success(pilot):
    from jujumate.screens.relation_data_screen import RelationDataScreen
    from jujumate.widgets.relation_data_view import RelationDataView

    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    entries = [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")]

    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(RelationDataView).update(rel, entries)
        await pilot.pause()
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-scroll").display is True


@pytest.mark.asyncio
async def test_relation_data_screen_fetch_error(pilot):
    from jujumate.screens.relation_data_screen import RelationDataScreen
    from jujumate.widgets.relation_data_view import RelationDataView

    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)

    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(RelationDataView).show_error(rel, "timeout")
        await pilot.pause()
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-empty").display is True
