import pytest
from textual.widgets import TabbedContent

from jujumate.app import JujuMateApp


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
