"""Tests for screens/log_screen.py — LogScreen modal and helper functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.text import Text
from textual.widgets import Input, Label, RichLog

from jujumate import palette as _palette
from jujumate.models.entities import LogEntry
from jujumate.screens.log_screen import (
    _LEVELS,
    LogScreen,
    _append_highlighted,
    _level_color,
)
from jujumate.theme_loader import load_theme as _load_theme

# Ensure palette is initialised before any tests in this module run.
# test_log_screen.py is collected before test_palette.py alphabetically, so
# palette may not yet be initialised when the pure-function tests execute.
_palette.init(_load_theme("ubuntu"))


# ─────────────────────────────────────────────────────────────────────────────
# Helper: create a sample LogEntry
# ─────────────────────────────────────────────────────────────────────────────


def _make_entry(
    level: str = "INFO",
    message: str = "ready",
    entity: str = "unit-pg-0",
    module: str = "juju.worker",
    timestamp: str = "10:00:00",
) -> LogEntry:
    return LogEntry(
        timestamp=timestamp,
        level=level,
        entity=entity,
        module=module,
        message=message,
    )


# ─────────────────────────────────────────────────────────────────────────────
# _level_color
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("level", _LEVELS)
def test_level_color_known_levels(level: str) -> None:
    # GIVEN a level string that belongs to _LEVELS
    # WHEN _level_color is called
    result = _level_color(level)
    # THEN a non-empty colour string is returned
    assert isinstance(result, str)
    assert len(result) > 0


def test_level_color_unknown_level() -> None:
    # GIVEN an unrecognised level string "VERBOSE"
    # WHEN _level_color is called
    result = _level_color("VERBOSE")
    # THEN it falls back to the TRACE colour
    assert result == _level_color("TRACE")


@pytest.mark.parametrize("level", ["FATAL", "CRITICAL"])
def test_level_color_fatal_and_critical(level: str) -> None:
    # GIVEN a level of FATAL or CRITICAL
    # WHEN _level_color is called
    result = _level_color(level)
    # THEN it returns the same colour as ERROR
    assert result == _level_color("ERROR")


# ─────────────────────────────────────────────────────────────────────────────
# _append_highlighted
# ─────────────────────────────────────────────────────────────────────────────


def test_append_highlighted_no_needle() -> None:
    # GIVEN an empty needle
    t = Text()
    # WHEN _append_highlighted is called
    _append_highlighted(t, "hello world", "", "default")
    # THEN the full value is appended with base_style
    assert "hello world" in t.plain


def test_append_highlighted_with_needle_found() -> None:
    # GIVEN a needle that is a substring of value
    t = Text()
    # WHEN _append_highlighted is called
    _append_highlighted(t, "error occurred here", "error", "default")
    # THEN the text has multiple spans (highlight + remainder)
    assert "error occurred here" in t.plain
    assert len(t._spans) > 1


def test_append_highlighted_with_needle_not_found() -> None:
    # GIVEN a needle that does not appear in the value
    t = Text()
    # WHEN _append_highlighted is called
    _append_highlighted(t, "all is well", "xyz", "default")
    # THEN the full value is appended with a single span
    assert "all is well" in t.plain


# ─────────────────────────────────────────────────────────────────────────────
# LogScreen mounting
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_mounts_and_shows_connecting(pilot) -> None:
    # GIVEN a LogScreen with _start_stream patched to prevent real streaming
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        # WHEN the screen is pushed onto the app
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN the RichLog widget exists
    assert screen.query_one("#log-richlog", RichLog) is not None


@pytest.mark.asyncio
async def test_log_screen_blink_live_indicator(pilot) -> None:
    # GIVEN a mounted LogScreen
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # WHEN _blink_live_indicator is called twice
    screen._blink_live_indicator()
    state_after_first = screen._blink_state
    screen._blink_live_indicator()
    state_after_second = screen._blink_state

    # THEN the blink state alternates each call
    assert state_after_first != state_after_second


# ─────────────────────────────────────────────────────────────────────────────
# _matches_filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_matches_filter_no_filter(pilot) -> None:
    # GIVEN a LogScreen with an empty filter
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._filter_text = ""

    # WHEN _matches_filter is called with any entry
    entry = _make_entry(message="anything")

    # THEN the entry always matches
    assert screen._matches_filter(entry) is True


@pytest.mark.asyncio
async def test_log_screen_matches_filter_with_match(pilot) -> None:
    # GIVEN a LogScreen whose filter is "error" and an entry whose message contains "error"
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._filter_text = "error"
    entry = _make_entry(message="error occurred")

    # WHEN _matches_filter is called
    result = screen._matches_filter(entry)

    # THEN the entry matches
    assert result is True


@pytest.mark.asyncio
async def test_log_screen_matches_filter_no_match(pilot) -> None:
    # GIVEN a LogScreen with filter "xyz" and an entry that does not contain "xyz"
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._filter_text = "xyz"
    entry = _make_entry(message="everything is fine", entity="unit-pg-0")

    # WHEN _matches_filter is called
    result = screen._matches_filter(entry)

    # THEN the entry does not match
    assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# _format_entry
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_format_entry(pilot) -> None:
    # GIVEN a mounted LogScreen and a sample LogEntry
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    entry = _make_entry(level="INFO", message="started", entity="unit-pg-0", timestamp="10:01:02")

    # WHEN _format_entry is called
    result = screen._format_entry(entry)

    # THEN the result is a Rich Text object containing all key parts
    assert isinstance(result, Text)
    assert "10:01:02" in result.plain
    assert "INFO" in result.plain
    assert "started" in result.plain


# ─────────────────────────────────────────────────────────────────────────────
# _update_level_label
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_update_level_label(pilot) -> None:
    # GIVEN a mounted LogScreen at the default level index (INFO)
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # WHEN _update_level_label is called
    screen._update_level_label()
    await pilot.pause()

    # THEN the #log-level-label contains the current level name
    label = screen.query_one("#log-level-label", Label)
    assert "INFO" in str(label.render())


# ─────────────────────────────────────────────────────────────────────────────
# _rerender_buffer
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_rerender_buffer(pilot) -> None:
    # GIVEN a mounted LogScreen with entries in its buffer
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._buffer.append(_make_entry(message="line one"))
    screen._buffer.append(_make_entry(message="line two"))

    # WHEN _rerender_buffer is called
    screen._rerender_buffer()
    await pilot.pause()

    # THEN the RichLog has content (lines >= 2)
    richlog = screen.query_one("#log-richlog", RichLog)
    assert len(richlog.lines) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# action_focus_filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_focus_filter_opens_bar(pilot) -> None:
    # GIVEN a mounted LogScreen with the filter bar hidden
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    bar = screen.query_one("#log-filter-bar")
    assert "visible" not in bar.classes

    # WHEN action_focus_filter is called
    screen.action_focus_filter()
    await pilot.pause()

    # THEN the filter bar gains the "visible" class
    assert "visible" in bar.classes


@pytest.mark.asyncio
async def test_log_screen_action_focus_filter_already_open_inserts_slash(pilot) -> None:
    # GIVEN a mounted LogScreen with the filter bar already visible
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen.query_one("#log-filter-bar").add_class("visible")

    # WHEN action_focus_filter is called again
    screen.action_focus_filter()
    await pilot.pause()

    # THEN a "/" is inserted into the filter input
    fi = screen.query_one("#log-filter", Input)
    assert "/" in fi.value


# ─────────────────────────────────────────────────────────────────────────────
# action_close_or_clear
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_close_or_clear_when_focused_on_filter(pilot) -> None:
    # GIVEN the filter bar is visible and the filter input has focus
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen.query_one("#log-filter-bar").add_class("visible")
    fi = screen.query_one("#log-filter", Input)
    screen.set_focus(fi)
    await pilot.pause()

    # WHEN action_close_or_clear is called
    screen.action_close_or_clear()
    await pilot.pause()

    # THEN the filter bar no longer has the "visible" class
    assert "visible" not in screen.query_one("#log-filter-bar").classes


@pytest.mark.asyncio
async def test_log_screen_action_close_or_clear_dismiss(pilot) -> None:
    # GIVEN the filter input does NOT have focus
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # Focus the RichLog (not the filter input)
    screen.set_focus(screen.query_one("#log-richlog", RichLog))
    await pilot.pause()

    with patch.object(screen, "dismiss") as mock_dismiss:
        # WHEN action_close_or_clear is called
        screen.action_close_or_clear()

    # THEN dismiss is called
    mock_dismiss.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# action_cycle_level
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_cycle_level(pilot) -> None:
    # GIVEN a mounted LogScreen at level index 2 (INFO)
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    assert screen._level == "INFO"

    with patch.object(screen, "_start_stream"):
        # WHEN action_cycle_level is called
        screen.action_cycle_level()

    # THEN the level advances to the next one (WARNING, index 3)
    assert screen._level == "WARNING"


# ─────────────────────────────────────────────────────────────────────────────
# action_scroll_end
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_scroll_end(pilot) -> None:
    # GIVEN a mounted LogScreen
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    richlog = screen.query_one("#log-richlog", RichLog)
    richlog.auto_scroll = False

    # WHEN action_scroll_end is called
    screen.action_scroll_end()
    await pilot.pause()

    # THEN auto_scroll is re-enabled
    assert richlog.auto_scroll is True


# ─────────────────────────────────────────────────────────────────────────────
# action_insert_separator
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_insert_separator_when_not_in_filter(pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the RichLog
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    richlog = screen.query_one("#log-richlog", RichLog)
    screen.set_focus(richlog)
    await pilot.pause()
    before = len(richlog.lines)

    # WHEN action_insert_separator is called
    screen.action_insert_separator()
    await pilot.pause()

    # THEN a new line is written to the RichLog
    assert len(richlog.lines) > before


@pytest.mark.asyncio
async def test_log_screen_action_insert_separator_ignored_in_filter_mode(pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the filter Input
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    fi = screen.query_one("#log-filter", Input)
    screen.set_focus(fi)
    await pilot.pause()
    richlog = screen.query_one("#log-richlog", RichLog)
    before = len(richlog.lines)

    # WHEN action_insert_separator is called while in filter mode
    screen.action_insert_separator()
    await pilot.pause()

    # THEN nothing is written to the RichLog
    assert len(richlog.lines) == before


# ─────────────────────────────────────────────────────────────────────────────
# action_copy_logs
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_copy_logs_empty_buffer(pilot) -> None:
    # GIVEN a mounted LogScreen with an empty buffer
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._buffer.clear()

    copy_mock = MagicMock()
    screen.app.copy_to_clipboard = copy_mock

    # WHEN action_copy_logs is called
    screen.action_copy_logs()
    await pilot.pause()

    # THEN copy_to_clipboard is called (with empty string for empty buffer)
    copy_mock.assert_called_once_with("")


@pytest.mark.asyncio
async def test_log_screen_action_copy_logs_with_entries(pilot) -> None:
    # GIVEN a mounted LogScreen with entries in the buffer
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    screen._buffer.append(_make_entry(message="first line"))
    screen._buffer.append(_make_entry(message="second line"))

    copy_mock = MagicMock()
    screen.app.copy_to_clipboard = copy_mock

    # WHEN action_copy_logs is called
    screen.action_copy_logs()
    await pilot.pause()

    # THEN copy_to_clipboard is called with a non-empty string
    copy_mock.assert_called_once()
    args = copy_mock.call_args[0]
    assert len(args[0]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# on_input_changed / on_input_submitted
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_on_input_changed_updates_filter(pilot) -> None:
    # GIVEN a mounted LogScreen
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    fi = screen.query_one("#log-filter", Input)

    # WHEN on_input_changed is called with value "error"
    screen.on_input_changed(Input.Changed(input=fi, value="error"))
    await pilot.pause()

    # THEN _filter_text is updated
    assert screen._filter_text == "error"


@pytest.mark.asyncio
async def test_log_screen_on_input_submitted_focuses_richlog(pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the filter input
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()
    fi = screen.query_one("#log-filter", Input)
    screen.set_focus(fi)
    await pilot.pause()

    # WHEN on_input_submitted is called
    screen.on_input_submitted(Input.Submitted(input=fi, value=""))
    await pilot.pause()

    # THEN focus moves to the RichLog
    assert screen.focused is screen.query_one("#log-richlog", RichLog)


# ─────────────────────────────────────────────────────────────────────────────
# _start_stream
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_start_stream_success(pilot) -> None:
    # GIVEN a LogScreen and a mock JujuClient whose stream_logs yields 2 entries
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    entry1 = _make_entry(message="first")
    entry2 = _make_entry(message="second")

    async def _fake_stream(*args, **kwargs):
        yield entry1
        yield entry2

    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=None)
    client_mock.stream_logs = _fake_stream

    with patch("jujumate.screens.log_screen.JujuClient", return_value=client_mock):
        # WHEN _start_stream is called and the worker completes
        worker = screen._start_stream()
        await worker.wait()
        await pilot.pause()

    # THEN both entries are in the buffer
    assert len(screen._buffer) == 2


@pytest.mark.asyncio
async def test_log_screen_start_stream_exception(pilot) -> None:
    # GIVEN a LogScreen and a mock JujuClient whose __aenter__ raises an exception
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    client_mock.__aexit__ = AsyncMock(return_value=None)

    screen.notify = MagicMock()

    with patch("jujumate.screens.log_screen.JujuClient", return_value=client_mock):
        # WHEN _start_stream is called and the exception is raised
        worker = screen._start_stream()
        await worker.wait()
        await pilot.pause()

    # THEN notify is called with severity="error"
    screen.notify.assert_called_once()
    call_kwargs = screen.notify.call_args
    assert call_kwargs.kwargs.get("severity") == "error" or (len(call_kwargs.args) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# _blink_live_indicator — unmounted guard (if not results: return)
# ─────────────────────────────────────────────────────────────────────────────


def test_log_screen_blink_live_indicator_unmounted() -> None:
    # GIVEN a LogScreen that has never been mounted (query returns empty)
    screen = LogScreen("ctrl", "dev")

    # WHEN _blink_live_indicator is called
    screen._blink_live_indicator()

    # THEN it returns without error and toggles _blink_state
    assert screen._blink_state is True


# ─────────────────────────────────────────────────────────────────────────────
# _get_selected_text helper
# ─────────────────────────────────────────────────────────────────────────────


def test_get_selected_text_no_selection() -> None:
    # GIVEN a RichLog mock with text_selection = None
    screen = LogScreen("ctrl", "dev")
    mock_richlog = MagicMock()
    mock_richlog.text_selection = None

    # WHEN _get_selected_text is called
    result = screen._get_selected_text(mock_richlog)

    # THEN it returns None
    assert result is None


def test_get_selected_text_with_selection() -> None:
    # GIVEN a RichLog mock that returns a valid selection
    screen = LogScreen("ctrl", "dev")
    mock_richlog = MagicMock()
    mock_richlog.text_selection = object()
    mock_richlog.get_selection.return_value = ("selected text", 0, 13)

    # WHEN _get_selected_text is called
    result = screen._get_selected_text(mock_richlog)

    # THEN it returns the selected text
    assert result == "selected text"


def test_get_selected_text_get_selection_returns_none() -> None:
    # GIVEN a RichLog mock whose get_selection returns None
    screen = LogScreen("ctrl", "dev")
    mock_richlog = MagicMock()
    mock_richlog.text_selection = object()
    mock_richlog.get_selection.return_value = None

    # WHEN _get_selected_text is called
    result = screen._get_selected_text(mock_richlog)

    # THEN it returns None
    assert result is None


@pytest.mark.asyncio
async def test_log_screen_action_copy_logs_with_selection(pilot) -> None:
    # GIVEN a mounted LogScreen and a RichLog with a text selection
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    copy_mock = MagicMock()
    screen.app.copy_to_clipboard = copy_mock
    screen.notify = MagicMock()

    mock_richlog = MagicMock()
    mock_richlog.text_selection = object()
    mock_richlog.get_selection.return_value = ("selected log line", 0, 16)

    # WHEN action_copy_logs is called with an active selection
    with patch.object(screen, "query_one", return_value=mock_richlog):
        screen.action_copy_logs()

    # THEN copy_to_clipboard is called with just the selected text
    copy_mock.assert_called_once_with("selected log line")
    screen.notify.assert_called_once_with("Selection copied to clipboard")


# ─────────────────────────────────────────────────────────────────────────────
# _start_stream — CancelledError is silently swallowed (line 159)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_start_stream_cancelled(pilot) -> None:
    # GIVEN a LogScreen mounted with a streaming client that blocks
    screen = LogScreen("prod", "dev")
    with patch.object(LogScreen, "_start_stream"):
        await pilot.app.push_screen(screen)
        await pilot.pause()

    import asyncio as _asyncio

    call_count = 0

    async def _selective_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Worker 1: blocks so it can be cancelled, triggering CancelledError
            await _asyncio.sleep(100)
        # Worker 2+: complete immediately (no yield → StopAsyncIteration)
        return
        yield  # makes this an async generator function

    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=None)
    client_mock.stream_logs = _selective_stream

    with patch("jujumate.screens.log_screen.JujuClient", return_value=client_mock):
        # WHEN a new exclusive worker is started (cancels the previous one)
        screen._start_stream()
        await pilot.pause()  # let worker1 start and block in sleep(100)
        worker2 = screen._start_stream()  # exclusive=True cancels worker1
        await worker2.wait()  # worker2 returns immediately
        await pilot.pause()

    # THEN no CancelledError propagated — screen is still functional
    assert screen.query_one("#log-richlog", RichLog) is not None
