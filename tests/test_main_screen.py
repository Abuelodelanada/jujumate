from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import TabbedContent

from jujumate.app import JujuMateApp
from jujumate.client.watcher import (
    AppsUpdated,
    CloudsUpdated,
    ConnectionFailed,
    ControllersUpdated,
    DataRefreshed,
    JujuPoller,
    ModelsUpdated,
    OffersUpdated,
    RelationsUpdated,
    UnitsUpdated,
)
from jujumate.config import JujuConfig, JujuConfigError
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, OfferInfo, RelationInfo, UnitInfo
from jujumate.settings import AppSettings


@pytest.mark.asyncio
async def test_app_mounts_main_screen():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_default_tab_is_clouds():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one(TabbedContent).active == "tab-clouds"


@pytest.mark.asyncio
async def test_keybinding_m_switches_to_models():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        assert app.screen.query_one(TabbedContent).active == "tab-models"


@pytest.mark.asyncio
async def test_keybinding_a_switches_to_apps():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        assert app.screen.query_one(TabbedContent).active == "tab-apps"


@pytest.mark.asyncio
async def test_keybinding_u_switches_to_units():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("u")
        assert app.screen.query_one(TabbedContent).active == "tab-units"


@pytest.mark.asyncio
async def test_keybinding_q_exits():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert app.return_value is None


@pytest.mark.asyncio
async def test_keybinding_r_triggers_refresh():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        # action_refresh_data calls notify() — verify app is still running
        assert app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_app_falls_back_when_theme_not_found():
    settings = AppSettings(theme="nonexistent-theme")
    app = JujuMateApp(settings=settings)
    async with app.run_test() as pilot:
        await pilot.pause()
        # App should still mount correctly despite unknown theme
        assert app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_message_handlers_update_views():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen

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
async def test_connection_failed_sets_subtitle():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.on_connection_failed(ConnectionFailed(error="timeout"))
        assert app.screen._is_connected is False


@pytest.mark.asyncio
async def test_action_refresh_data_without_poller():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # _poller is None at this point — should not crash
        await app.screen.action_refresh_data()
        assert app.screen.__class__.__name__ == "MainScreen"


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
async def test_connect_and_poll_connection_failure():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        with patch(
            "jujumate.screens.main_screen.load_config",
            side_effect=JujuConfigError("no config"),
        ):
            await screen._connect_and_poll()
        await pilot.pause()
        assert screen._is_connected is False


@pytest.mark.asyncio
async def test_connect_and_poll_success():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
async def test_action_refresh_data_with_poller():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen._poller = AsyncMock(spec=JujuPoller)
        await screen.action_refresh_data()
        screen._poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_selected_switches_to_controllers_and_filters():
    from jujumate.widgets.clouds_view import CloudsView
    from jujumate.widgets.controllers_view import ControllersView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        # Populate data
        screen._all_controllers = [
            ControllerInfo("prod", "aws", "", "3.4.0", 1),
            ControllerInfo("dev", "lxd", "", "3.4.0", 1),
        ]
        # Simulate cloud selection
        screen.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
        await pilot.pause()
        # Should switch to controllers tab
        assert app.screen.query_one(TabbedContent).active == "tab-controllers"
        # Should only show aws controller
        ctrl_view = screen.query_one("#controllers-view", ControllersView)
        assert ctrl_view.query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_controller_selected_switches_to_models_and_filters():
    from jujumate.widgets.controllers_view import ControllersView
    from jujumate.widgets.models_view import ModelsView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen._all_models = [
            ModelInfo("dev", "prod", "aws", "", "available"),
            ModelInfo("staging", "other-ctrl", "aws", "", "available"),
        ]
        screen.on_controllers_view_controller_selected(
            ControllersView.ControllerSelected(name="prod")
        )
        await pilot.pause()
        assert app.screen.query_one(TabbedContent).active == "tab-models"
        models_view = screen.query_one("#models-view", ModelsView)
        assert models_view.query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_model_selected_switches_to_status_and_filters():
    from jujumate.widgets.apps_view import AppsView
    from jujumate.widgets.models_view import ModelsView
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen._all_apps = [
            AppInfo("pg", "dev", "pg", "14/stable", 1),
            AppInfo("mysql", "prod", "mysql", "8/stable", 1),
        ]
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_status_details = AsyncMock(return_value=([], []))
        with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
            screen._selected_controller = "ctrl"
            screen.on_models_view_model_selected(ModelsView.ModelSelected(name="ctrl/dev"))
            await pilot.pause()
            await pilot.pause()
        assert app.screen.query_one(TabbedContent).active == "tab-status"
        # Apps tab still filtered by model
        apps_view = screen.query_one("#apps-view", AppsView)
        assert apps_view.query_one("DataTable").row_count == 1
        # Status view shows apps for selected model
        status_view = screen.query_one("#status-view", StatusView)
        assert status_view.query_one("#status-apps-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_app_selected_switches_to_units_and_filters():
    from jujumate.widgets.apps_view import AppsView
    from jujumate.widgets.units_view import UnitsView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen._all_units = [
            UnitInfo("pg/0", "pg", "0", "active", "idle"),
            UnitInfo("mysql/0", "mysql", "0", "active", "idle"),
        ]
        screen.on_apps_view_app_selected(AppsView.AppSelected(name="pg"))
        await pilot.pause()
        assert app.screen.query_one(TabbedContent).active == "tab-units"
        units_view = screen.query_one("#units-view", UnitsView)
        assert units_view.query_one("DataTable").row_count == 1


@pytest.mark.asyncio
async def test_clear_filter_resets_all_selections():
    from jujumate.widgets.controllers_view import ControllersView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
        assert ctrl_view.query_one("DataTable").row_count == 2


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
async def test_relations_updated_populates_status_view():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
async def test_relations_updated_replaces_existing_for_same_model():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
async def test_offers_updated_populates_status_view():
    from jujumate.widgets.status_view import StatusView

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
async def test_fetch_relations_worker_posts_message():
    from jujumate.models.entities import RelationInfo

    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_status_details = AsyncMock(return_value=([rel], []))
        with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
            screen._fetch_relations("ctrl", "dev")
            await pilot.pause()
            await pilot.pause()
        assert any(r.model == "dev" for r in screen._all_relations)


@pytest.mark.asyncio
async def test_fetch_relations_worker_handles_exception():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
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
