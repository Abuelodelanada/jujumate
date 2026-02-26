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
    UnitsUpdated,
)
from jujumate.config import JujuConfig, JujuConfigError
from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo
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
        assert app.sub_title == "⣾ Live  ·  12:00:00"


@pytest.mark.asyncio
async def test_connection_failed_sets_subtitle():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.on_connection_failed(ConnectionFailed(error="timeout"))
        assert app.sub_title == "⚠ Disconnected"


@pytest.mark.asyncio
async def test_action_refresh_data_without_poller():
    app = JujuMateApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # _poller is None at this point — should not crash
        await app.screen.action_refresh_data()
        assert app.screen.__class__.__name__ == "MainScreen"


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
        assert app.sub_title == "⚠ Disconnected"


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
