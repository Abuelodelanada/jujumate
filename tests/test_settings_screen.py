"""Tests for SettingsScreen and its helpers."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from textual.containers import Vertical
from textual.widgets import Select

from jujumate.screens.settings_screen import (
    _NO_CONTROLLER,
    SettingsScreen,
    _nearest_refresh,
)
from jujumate.settings import AppSettings

# ─────────────────────────────────────────────────────────────────────────────
# _nearest_refresh
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(2, 2, id="exact-2"),
        pytest.param(5, 5, id="exact-5"),
        pytest.param(10, 10, id="exact-10"),
        pytest.param(3, 2, id="snaps-lower"),
        pytest.param(9, 10, id="snaps-higher"),
        pytest.param(30, 10, id="large-value"),
    ],
)
def test_nearest_refresh(value: int, expected: int) -> None:
    # GIVEN a value that may or may not match an allowed option
    # WHEN _nearest_refresh is called
    result = _nearest_refresh(value)
    # THEN it returns the nearest allowed option
    assert result == expected


# ─────────────────────────────────────────────────────────────────────────────
# SettingsScreen compose / on_mount
# ─────────────────────────────────────────────────────────────────────────────


def _make_settings(**kwargs: object) -> AppSettings:
    defaults: dict = dict(
        refresh_interval=5,
        default_controller=None,
        log_level=logging.INFO,
        theme="ubuntu",
    )
    defaults.update(kwargs)
    return AppSettings(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_settings_screen_compose_shows_three_sections(pilot):
    # GIVEN a SettingsScreen with default settings and no controllers
    screen = SettingsScreen(_make_settings(), controller_names=[])

    # WHEN the screen is pushed
    await pilot.app.push_screen(screen)
    await pilot.pause()

    # THEN all three setting selects are rendered (one per section)

    assert pilot.app.screen.query_one("#select-theme", Select) is not None
    assert pilot.app.screen.query_one("#select-refresh", Select) is not None
    assert pilot.app.screen.query_one("#select-log-level", Select) is not None


@pytest.mark.asyncio
async def test_settings_screen_on_mount_sets_border_title(pilot):
    # GIVEN a SettingsScreen
    screen = SettingsScreen(_make_settings(), controller_names=[])

    # WHEN the screen is pushed
    await pilot.app.push_screen(screen)
    await pilot.pause()

    # THEN the panel border_title is "Settings"

    panel = pilot.app.screen.query_one("#settings-panel", Vertical)
    assert panel.border_title == "Settings"


# ─────────────────────────────────────────────────────────────────────────────
# on_select_changed
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_screen_theme_change_calls_switch_theme(pilot):
    # GIVEN a SettingsScreen pushed onto the app
    settings = _make_settings(theme="ubuntu")
    screen = SettingsScreen(settings, controller_names=[])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with (
        patch.object(pilot.app, "switch_theme") as mock_switch,
        patch("jujumate.screens.settings_screen.save_settings") as mock_save,
    ):
        # WHEN a different theme is selected
        select = pilot.app.screen.query_one("#select-theme", Select)
        select.value = "dark"
        await pilot.pause()

        # THEN switch_theme is called with the new theme and settings are persisted
        mock_switch.assert_called_with("dark")
        mock_save.assert_called()


@pytest.mark.asyncio
async def test_settings_screen_refresh_change_updates_settings(pilot):
    # GIVEN a SettingsScreen with refresh_interval=5
    settings = _make_settings(refresh_interval=5)
    screen = SettingsScreen(settings, controller_names=[])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with patch("jujumate.screens.settings_screen.save_settings") as mock_save:
        # WHEN refresh interval is changed to 10

        select = pilot.app.screen.query_one("#select-refresh", Select)
        select.value = 10
        await pilot.pause()

        # THEN the internal settings are updated and persisted
        assert screen._settings.refresh_interval == 10
        mock_save.assert_called()


@pytest.mark.asyncio
async def test_settings_screen_controller_change_updates_settings(pilot):
    # GIVEN a SettingsScreen with controller options
    settings = _make_settings(default_controller=None)
    screen = SettingsScreen(settings, controller_names=["prod", "staging"])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with patch("jujumate.screens.settings_screen.save_settings") as mock_save:
        # WHEN a controller is selected

        select = pilot.app.screen.query_one("#select-controller", Select)
        select.value = "prod"
        await pilot.pause()

        # THEN the internal settings are updated and persisted
        assert screen._settings.default_controller == "prod"
        mock_save.assert_called()


@pytest.mark.asyncio
async def test_settings_screen_controller_none_clears_default(pilot):
    # GIVEN a SettingsScreen with a controller already selected
    settings = _make_settings(default_controller="prod")
    screen = SettingsScreen(settings, controller_names=["prod"])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with patch("jujumate.screens.settings_screen.save_settings") as mock_save:
        # WHEN "— none —" is selected

        select = pilot.app.screen.query_one("#select-controller", Select)
        select.value = _NO_CONTROLLER
        await pilot.pause()

        # THEN default_controller is cleared to None
        assert screen._settings.default_controller is None
        mock_save.assert_called()


@pytest.mark.asyncio
async def test_settings_screen_log_level_change_applies_immediately(pilot):
    # GIVEN a SettingsScreen with log level INFO
    settings = _make_settings(log_level=logging.INFO)
    screen = SettingsScreen(settings, controller_names=[])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with (
        patch("jujumate.screens.settings_screen.save_settings"),
        patch("jujumate.screens.settings_screen.logging") as mock_logging,
    ):
        mock_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_logger
        mock_logging.DEBUG = logging.DEBUG

        # WHEN log level is changed to DEBUG

        select = pilot.app.screen.query_one("#select-log-level", Select)
        select.value = logging.DEBUG
        await pilot.pause()

        # THEN setLevel is called immediately and settings updated
        assert screen._settings.log_level == logging.DEBUG


# ─────────────────────────────────────────────────────────────────────────────
# action_save_and_close
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_screen_escape_dismisses_with_settings(pilot):
    # GIVEN a SettingsScreen with specific settings
    settings = _make_settings(refresh_interval=10)
    screen = SettingsScreen(settings, controller_names=[])
    result: list[AppSettings | None] = []
    await pilot.app.push_screen(screen, result.append)
    await pilot.pause()

    # WHEN Escape is pressed
    await pilot.press("escape")
    await pilot.pause()

    # THEN the screen is dismissed and the settings are returned
    assert not isinstance(pilot.app.screen, SettingsScreen)
    assert len(result) == 1
    assert result[0] is not None
    assert result[0].refresh_interval == 10


@pytest.mark.asyncio
async def test_settings_screen_select_blank_value_does_nothing(pilot):
    # GIVEN a SettingsScreen pushed onto the app
    settings = _make_settings(refresh_interval=5)
    screen = SettingsScreen(settings, controller_names=[])
    await pilot.app.push_screen(screen)
    await pilot.pause()

    with patch("jujumate.screens.settings_screen.save_settings") as mock_save:
        # WHEN on_select_changed is triggered with a BLANK value
        mock_event = MagicMock()
        mock_event.value = Select.BLANK
        screen.on_select_changed(mock_event)
        await pilot.pause()

        # THEN nothing is persisted and settings are unchanged
        mock_save.assert_not_called()
        assert screen._settings.refresh_interval == 5
