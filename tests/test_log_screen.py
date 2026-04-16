"""Tests for screens/log_screen.py — LogScreen modal and helper functions."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.text import Text
from textual.app import SuspendNotSupported
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
async def test_log_screen_mounts_and_shows_connecting(log_screen) -> None:
    # GIVEN a LogScreen with _start_stream patched to prevent real streaming
    # WHEN the screen is pushed onto the app (done by log_screen fixture)

    # THEN the RichLog widget exists
    assert log_screen.query_one("#log-richlog", RichLog) is not None


@pytest.mark.asyncio
async def test_log_screen_blink_live_indicator(log_screen) -> None:
    # GIVEN a mounted LogScreen

    # WHEN _blink_live_indicator is called twice
    log_screen._blink_live_indicator()
    state_after_first = log_screen._blink_state
    log_screen._blink_live_indicator()
    state_after_second = log_screen._blink_state

    # THEN the blink state alternates each call
    assert state_after_first != state_after_second


# ─────────────────────────────────────────────────────────────────────────────
# _matches_filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filter_text, message, entity, expected",
    [
        ("", "anything", "unit-x", True),
        ("error", "error occurred", "unit-x", True),
        ("xyz", "everything is fine", "unit-pg-0", False),
    ],
)
async def test_log_screen_matches_filter(
    log_screen, filter_text: str, message: str, entity: str, expected: bool
) -> None:
    # GIVEN a LogScreen with the given filter text
    log_screen._filter_text = filter_text
    entry = _make_entry(message=message, entity=entity)

    # WHEN _matches_filter is called
    result = log_screen._matches_filter(entry)

    # THEN result matches expected
    assert result is expected


# ─────────────────────────────────────────────────────────────────────────────
# _format_entry
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_format_entry(log_screen) -> None:
    # GIVEN a mounted LogScreen and a sample LogEntry
    entry = _make_entry(level="INFO", message="started", entity="unit-pg-0", timestamp="10:01:02")

    # WHEN _format_entry is called
    result = log_screen._format_entry(entry)

    # THEN the result is a Rich Text object containing all key parts
    assert isinstance(result, Text)
    assert "10:01:02" in result.plain
    assert "INFO" in result.plain
    assert "started" in result.plain


# ─────────────────────────────────────────────────────────────────────────────
# _update_level_label
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_update_level_label(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen at the default level index (INFO)

    # WHEN _update_level_label is called
    log_screen._update_level_label()
    await pilot.pause()

    # THEN the #log-level-label contains the current level name
    label = log_screen.query_one("#log-level-label", Label)
    assert "INFO" in str(label.render())


# ─────────────────────────────────────────────────────────────────────────────
# _rerender_buffer
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_rerender_buffer(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with entries in its buffer
    log_screen._buffer.append(_make_entry(message="line one"))
    log_screen._buffer.append(_make_entry(message="line two"))

    # WHEN _rerender_buffer is called
    log_screen._rerender_buffer()
    await pilot.pause()

    # THEN the RichLog has content (lines >= 2)
    richlog = log_screen.query_one("#log-richlog", RichLog)
    assert len(richlog.lines) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# action_focus_filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_focus_filter_opens_bar(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with the filter bar hidden
    bar = log_screen.query_one("#log-filter-bar")
    assert "visible" not in bar.classes

    # WHEN action_focus_filter is called
    log_screen.action_focus_filter()
    await pilot.pause()

    # THEN the filter bar gains the "visible" class
    assert "visible" in bar.classes


@pytest.mark.asyncio
async def test_log_screen_action_focus_filter_already_open_inserts_slash(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with the filter bar already visible
    log_screen.query_one("#log-filter-bar").add_class("visible")

    # WHEN action_focus_filter is called again
    log_screen.action_focus_filter()
    await pilot.pause()

    # THEN a "/" is inserted into the filter input
    fi = log_screen.query_one("#log-filter", Input)
    assert "/" in fi.value


# ─────────────────────────────────────────────────────────────────────────────
# action_close_or_clear
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_close_or_clear_when_focused_on_filter(log_screen, pilot) -> None:
    # GIVEN the filter bar is visible and the filter input has focus
    log_screen.query_one("#log-filter-bar").add_class("visible")
    fi = log_screen.query_one("#log-filter", Input)
    log_screen.set_focus(fi)
    await pilot.pause()

    # WHEN action_close_or_clear is called
    log_screen.action_close_or_clear()
    await pilot.pause()

    # THEN the filter bar no longer has the "visible" class
    assert "visible" not in log_screen.query_one("#log-filter-bar").classes


@pytest.mark.asyncio
async def test_log_screen_action_close_or_clear_dismiss(log_screen, pilot) -> None:
    # GIVEN the filter input does NOT have focus
    # Focus the RichLog (not the filter input)
    log_screen.set_focus(log_screen.query_one("#log-richlog", RichLog))
    await pilot.pause()

    with patch.object(log_screen, "dismiss") as mock_dismiss:
        # WHEN action_close_or_clear is called
        log_screen.action_close_or_clear()

    # THEN dismiss is called
    mock_dismiss.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# action_cycle_level
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_cycle_level(log_screen) -> None:
    # GIVEN a mounted LogScreen at level index 2 (INFO)
    assert log_screen._level == "INFO"

    with patch.object(log_screen, "_start_stream"):
        # WHEN action_cycle_level is called
        log_screen.action_cycle_level()

    # THEN the level advances to the next one (WARNING, index 3)
    assert log_screen._level == "WARNING"


# ─────────────────────────────────────────────────────────────────────────────
# action_scroll_end
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_scroll_end(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen
    richlog = log_screen.query_one("#log-richlog", RichLog)
    richlog.auto_scroll = False

    # WHEN action_scroll_end is called
    log_screen.action_scroll_end()
    await pilot.pause()

    # THEN auto_scroll is re-enabled
    assert richlog.auto_scroll is True


# ─────────────────────────────────────────────────────────────────────────────
# action_insert_separator
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_insert_separator_when_not_in_filter(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the RichLog
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    before = len(richlog.lines)

    # WHEN action_insert_separator is called
    log_screen.action_insert_separator()
    await pilot.pause()

    # THEN a new line is written to the RichLog
    assert len(richlog.lines) > before


@pytest.mark.asyncio
async def test_log_screen_action_insert_separator_ignored_in_filter_mode(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the filter Input
    fi = log_screen.query_one("#log-filter", Input)
    log_screen.set_focus(fi)
    await pilot.pause()
    richlog = log_screen.query_one("#log-richlog", RichLog)
    before = len(richlog.lines)

    # WHEN action_insert_separator is called while in filter mode
    log_screen.action_insert_separator()
    await pilot.pause()

    # THEN nothing is written to the RichLog
    assert len(richlog.lines) == before


# ─────────────────────────────────────────────────────────────────────────────
# action_copy_logs
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_action_copy_logs_empty_buffer(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with an empty buffer
    log_screen._buffer.clear()

    copy_mock = MagicMock()
    log_screen.app.copy_to_clipboard = copy_mock

    # WHEN action_copy_logs is called
    log_screen.action_copy_logs()
    await pilot.pause()

    # THEN copy_to_clipboard is called (with empty string for empty buffer)
    copy_mock.assert_called_once_with("")


@pytest.mark.asyncio
async def test_log_screen_action_copy_logs_with_entries(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with entries in the buffer
    log_screen._buffer.append(_make_entry(message="first line"))
    log_screen._buffer.append(_make_entry(message="second line"))

    copy_mock = MagicMock()
    log_screen.app.copy_to_clipboard = copy_mock

    # WHEN action_copy_logs is called
    log_screen.action_copy_logs()
    await pilot.pause()

    # THEN copy_to_clipboard is called with a non-empty string
    copy_mock.assert_called_once()
    args = copy_mock.call_args[0]
    assert len(args[0]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# on_input_changed / on_input_submitted
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_on_input_changed_updates_filter(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen
    fi = log_screen.query_one("#log-filter", Input)

    # WHEN on_input_changed is called with value "error"
    log_screen.on_input_changed(Input.Changed(input=fi, value="error"))
    await pilot.pause()

    # THEN _filter_text is updated
    assert log_screen._filter_text == "error"


@pytest.mark.asyncio
async def test_log_screen_on_input_submitted_focuses_richlog(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the filter input
    fi = log_screen.query_one("#log-filter", Input)
    log_screen.set_focus(fi)
    await pilot.pause()

    # WHEN on_input_submitted is called
    log_screen.on_input_submitted(Input.Submitted(input=fi, value=""))
    await pilot.pause()

    # THEN focus moves to the RichLog
    assert log_screen.focused is log_screen.query_one("#log-richlog", RichLog)


# ─────────────────────────────────────────────────────────────────────────────
# _start_stream
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_start_stream_success(log_screen, pilot) -> None:
    # GIVEN a LogScreen and a mock JujuClient whose stream_logs yields 2 entries
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
        worker = log_screen._start_stream()
        await worker.wait()
        await pilot.pause()

    # THEN both entries are in the buffer
    assert len(log_screen._buffer) == 2


@pytest.mark.asyncio
async def test_log_screen_start_stream_exception(log_screen, pilot) -> None:
    # GIVEN a LogScreen and a mock JujuClient whose __aenter__ raises an exception
    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    client_mock.__aexit__ = AsyncMock(return_value=None)

    log_screen.notify = MagicMock()

    with patch("jujumate.screens.log_screen.JujuClient", return_value=client_mock):
        # WHEN _start_stream is called and the exception is raised
        worker = log_screen._start_stream()
        await worker.wait()
        await pilot.pause()

    # THEN notify is called with severity="error"
    log_screen.notify.assert_called_once()
    call_kwargs = log_screen.notify.call_args
    assert call_kwargs.kwargs.get("severity") == "error" or (len(call_kwargs.args) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# _blink_live_indicator — unmounted guard (if not results: return)
# ─────────────────────────────────────────────────────────────────────────────


def test_log_screen_blink_live_indicator_unmounted() -> None:
    # GIVEN a LogScreen that has never been mounted (query returns empty)
    screen = LogScreen("ctrl", "dev")

    # WHEN _blink_live_indicator is called
    screen._blink_live_indicator()

    # THEN it returns without error and _blink_state is not toggled (no widget to update)
    assert screen._blink_state is False


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
async def test_log_screen_action_copy_logs_with_selection(log_screen) -> None:
    # GIVEN a mounted LogScreen and a RichLog with a text selection
    copy_mock = MagicMock()
    log_screen.app.copy_to_clipboard = copy_mock
    log_screen.notify = MagicMock()

    mock_richlog = MagicMock()
    mock_richlog.text_selection = object()
    mock_richlog.get_selection.return_value = ("selected log line", 0, 16)

    # WHEN action_copy_logs is called with an active selection
    with patch.object(log_screen, "query_one", return_value=mock_richlog):
        log_screen.action_copy_logs()

    # THEN copy_to_clipboard is called with just the selected text
    copy_mock.assert_called_once_with("selected log line")
    log_screen.notify.assert_called_once_with("Selection copied to clipboard")


# ─────────────────────────────────────────────────────────────────────────────
# _start_stream — CancelledError is silently swallowed (line 159)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_start_stream_cancelled(log_screen, pilot) -> None:
    # GIVEN a LogScreen mounted with a streaming client that blocks
    call_count = 0

    async def _selective_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Worker 1: blocks so it can be cancelled, triggering CancelledError
            await asyncio.sleep(100)
        # Worker 2+: complete immediately (no yield → StopAsyncIteration)
        return
        yield  # makes this an async generator function

    client_mock = AsyncMock()
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=None)
    client_mock.stream_logs = _selective_stream

    with patch("jujumate.screens.log_screen.JujuClient", return_value=client_mock):
        # WHEN a new exclusive worker is started (cancels the previous one)
        log_screen._start_stream()
        await pilot.pause()  # let worker1 start and block in sleep(100)
        worker2 = log_screen._start_stream()  # exclusive=True cancels worker1
        await worker2.wait()  # worker2 returns immediately
        await pilot.pause()

    # THEN no CancelledError propagated — screen is still functional
    assert log_screen.query_one("#log-richlog", RichLog) is not None


# ─────────────────────────────────────────────────────────────────────────────
# action_toggle_pause
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_toggle_pause_freezes_indicator(log_screen, pilot) -> None:
    # GIVEN a mounted LogScreen with focus on the RichLog (not the filter)
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    assert log_screen._paused is False

    # WHEN action_toggle_pause is called
    log_screen.action_toggle_pause()
    await pilot.pause()

    # THEN the screen is paused and the indicator shows PAUSED
    assert log_screen._paused is True
    indicator = log_screen.query_one("#log-live-indicator", Label)
    assert "PAUSED" in str(indicator.render())


@pytest.mark.asyncio
async def test_log_screen_toggle_pause_resumes_and_rerenders(log_screen, pilot) -> None:
    # GIVEN a paused LogScreen with one entry in the buffer
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen._paused = True
    log_screen._buffer.append(_make_entry(message="buffered while paused"))

    # WHEN action_toggle_pause is called to resume
    log_screen.action_toggle_pause()
    await pilot.pause()

    # THEN the screen is no longer paused and the buffer entry is rendered
    assert log_screen._paused is False
    assert any("buffered while paused" in line.text for line in richlog.lines)


@pytest.mark.asyncio
async def test_log_screen_blink_skipped_while_paused(log_screen, pilot) -> None:
    # GIVEN a paused LogScreen
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen.action_toggle_pause()
    await pilot.pause()
    assert log_screen._paused is True
    state_before = log_screen._blink_state

    # WHEN _blink_live_indicator fires (as if the interval ticked)
    log_screen._blink_live_indicator()

    # THEN _blink_state is not toggled
    assert log_screen._blink_state == state_before


@pytest.mark.asyncio
async def test_log_screen_toggle_pause_ignored_when_filter_focused(log_screen, pilot) -> None:
    # GIVEN the filter input is focused
    filter_input = log_screen.query_one("#log-filter", Input)
    log_screen.set_focus(filter_input)
    await pilot.pause()

    # WHEN action_toggle_pause is called
    log_screen.action_toggle_pause()

    # THEN the screen is NOT paused (space is a text character in filter mode)
    assert log_screen._paused is False


# ─────────────────────────────────────────────────────────────────────────────
# action_view_in_pager
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_screen_view_in_pager_calls_suspend_and_pager(log_screen, pilot) -> None:
    # GIVEN a LogScreen with entries in the buffer and focus on the RichLog
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen._buffer.append(_make_entry(message="hello from buffer"))

    suspend_calls: list[str] = []

    class _FakeSuspend:
        def __enter__(self) -> "_FakeSuspend":
            suspend_calls.append("enter")
            return self

        def __exit__(self, *_: object) -> None:
            suspend_calls.append("exit")

    # WHEN action_view_in_pager is called with pager and suspend mocked
    with (
        patch("jujumate.screens.log_screen.subprocess.run") as run_mock,
        patch.object(log_screen.app, "suspend", return_value=_FakeSuspend()),
    ):
        log_screen.action_view_in_pager()

    # THEN app.suspend() was entered/exited and the pager was launched
    assert suspend_calls == ["enter", "exit"]
    run_mock.assert_called_once()
    pager_args = run_mock.call_args[0][0]
    assert isinstance(pager_args, list)
    assert pager_args[0] in ("less", os.environ.get("PAGER", "less"))


@pytest.mark.asyncio
async def test_log_screen_view_in_pager_empty_buffer_shows_warning(log_screen, pilot) -> None:
    # GIVEN a LogScreen with an empty buffer and focus on the RichLog
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen._buffer.clear()

    notify_calls: list[str] = []

    # WHEN action_view_in_pager is called
    with patch.object(log_screen, "notify", side_effect=lambda msg, **kw: notify_calls.append(msg)):
        log_screen.action_view_in_pager()

    # THEN a warning notification is shown and no pager is launched
    assert any("No log lines" in msg for msg in notify_calls)


@pytest.mark.asyncio
async def test_log_screen_view_in_pager_ignored_when_filter_focused(log_screen, pilot) -> None:
    # GIVEN the filter input is focused
    filter_input = log_screen.query_one("#log-filter", Input)
    log_screen.set_focus(filter_input)
    await pilot.pause()
    log_screen._buffer.append(_make_entry(message="some log"))

    # WHEN action_view_in_pager is called
    with patch("jujumate.screens.log_screen.subprocess.run") as run_mock:
        log_screen.action_view_in_pager()

    # THEN the pager is not launched
    run_mock.assert_not_called()


@pytest.mark.asyncio
async def test_log_screen_view_in_pager_suspend_not_supported(log_screen, pilot) -> None:
    # GIVEN a LogScreen with entries and RichLog focused
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen._buffer.append(_make_entry(message="some log"))

    notify_calls: list[dict] = []

    def _capture_notify(msg: str, **kw: object) -> None:
        notify_calls.append({"msg": msg, **kw})

    # WHEN action_view_in_pager is called and suspend raises SuspendNotSupported
    with (
        patch.object(log_screen.app, "suspend", side_effect=SuspendNotSupported("no support")),
        patch.object(log_screen, "notify", side_effect=_capture_notify),
    ):
        log_screen.action_view_in_pager()

    # THEN a specific error notification is shown
    assert any("Suspend not supported" in c["msg"] for c in notify_calls)
    assert all(c.get("severity") == "error" for c in notify_calls)


@pytest.mark.asyncio
async def test_log_screen_view_in_pager_pager_not_found(log_screen, pilot) -> None:
    # GIVEN a LogScreen with entries, RichLog focused and an unavailable pager
    richlog = log_screen.query_one("#log-richlog", RichLog)
    log_screen.set_focus(richlog)
    await pilot.pause()
    log_screen._buffer.append(_make_entry(message="some log"))

    notify_calls: list[dict] = []

    def _capture_notify(msg: str, **kw: object) -> None:
        notify_calls.append({"msg": msg, **kw})

    class _FakeSuspend:
        def __enter__(self) -> "_FakeSuspend":
            return self

        def __exit__(self, *_: object) -> None:
            pass

    # WHEN action_view_in_pager is called and the pager binary is missing
    with (
        patch.object(log_screen.app, "suspend", return_value=_FakeSuspend()),
        patch(
            "jujumate.screens.log_screen.subprocess.run",
            side_effect=FileNotFoundError("no such file"),
        ),
        patch.object(log_screen, "notify", side_effect=_capture_notify),
    ):
        log_screen.action_view_in_pager()

    # THEN a specific error notification about the missing pager is shown
    assert any("Pager not found" in c["msg"] for c in notify_calls)
    assert all(c.get("severity") == "error" for c in notify_calls)
