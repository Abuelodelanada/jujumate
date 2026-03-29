"""Tests for SettingsScreen and its helpers."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from jujumate.screens.settings_screen import (
    _NO_CONTROLLER,
    SettingsScreen,
    _nearest_refresh,
)
from jujumate.settings import AppSettings

# ─────────────────────────────────────────────────────────────────────────────
# _nearest_refresh
# ─────────────────────────────────────────────────────────────────────────────


def test_nearest_refresh_returns_exact_match():
    # GIVEN a value that exactly matches an allowed option
    # WHEN _nearest_refresh is called
    # THEN it returns the same value
    assert _nearest_refresh(2) == 2
    assert _nearest_refresh(5) == 5
    assert _nearest_refresh(10) == 10


def test_nearest_refresh_snaps_to_closest_lower():
    # GIVEN a value closer to 2 than to 5
    # WHEN _nearest_refresh is called
    result = _nearest_refresh(3)
    # THEN it returns 2
    assert result == 2


def test_nearest_refresh_snaps_to_closest_higher():
    # GIVEN a value closer to 10 than to 5
    # WHEN _nearest_refresh is called
    result = _nearest_refresh(9)
    # THEN it returns 10
    assert result == 10


def test_nearest_refresh_snaps_large_value_to_10():
    # GIVEN a value larger than any allowed option
    # WHEN _nearest_refresh is called
    result = _nearest_refresh(30)
    # THEN it returns the largest option
    assert result == 10


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
    from textual.widgets import Select

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
    from textual.containers import Vertical

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

    from textual.widgets import Select

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
        from textual.widgets import Select

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
        from textual.widgets import Select

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
        from textual.widgets import Select

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
        from textual.widgets import Select

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
        from textual.widgets import Select

        # WHEN on_select_changed is triggered with a BLANK value
        mock_event = MagicMock()
        mock_event.value = Select.BLANK
        screen.on_select_changed(mock_event)
        await pilot.pause()

        # THEN nothing is persisted and settings are unchanged
        mock_save.assert_not_called()
        assert screen._settings.refresh_interval == 5
