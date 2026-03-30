"""Tests for HealthView widget and related health-tab integration in MainScreen."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.containers import Vertical
from textual.widgets import DataTable, Label, TabbedContent

from jujumate import palette
from jujumate.models.entities import AppInfo, ModelInfo, UnitInfo
from jujumate.widgets.health_view import (
    _HEALTHY,
    HealthView,
    _colored_dot,
    _colored_status,
    _model_worst_status,
    _rank,
)
from jujumate.widgets.status_view import StatusView

# ─────────────────────────────────────────────────────────────────────────────
# Helper factories
# ─────────────────────────────────────────────────────────────────────────────


def _app(
    name: str, model: str = "dev", controller: str = "ctrl", status: str = "active"
) -> AppInfo:
    return AppInfo(name, model, name, "stable", 1, status=status, controller=controller)


def _unit(
    name: str,
    app: str = "pg",
    model: str = "dev",
    controller: str = "ctrl",
    workload_status: str = "active",
    message: str = "",
) -> UnitInfo:
    return UnitInfo(
        name,
        app,
        "0",
        workload_status,
        "idle",
        "10.0.0.1",
        model=model,
        controller=controller,
        message=message,
    )


def _model(name: str = "dev", controller: str = "ctrl") -> ModelInfo:
    return ModelInfo(name, controller, "aws", "us-east-1", "available")


async def _mount_health_view(pilot) -> HealthView:
    view = HealthView(id="test-hv")
    await pilot.app.screen.mount(view)
    await pilot.pause()
    return view


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests: _rank
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,expected_rank",
    [
        pytest.param("error", 0, id="error"),
        pytest.param("blocked", 1, id="blocked"),
        pytest.param("maintenance", 2, id="maintenance"),
        pytest.param("waiting", 3, id="waiting"),
        pytest.param("executing", 3, id="executing"),
        pytest.param("active", 4, id="active"),
        pytest.param("idle", 4, id="idle"),
        pytest.param("started", 4, id="started"),
    ],
)
def test_rank_known_statuses(status: str, expected_rank: int) -> None:
    # GIVEN a known status string
    # WHEN _rank is called
    result = _rank(status)
    # THEN the returned rank matches the expected severity order
    assert result == expected_rank


def test_rank_unknown_status_defaults_to_waiting_rank() -> None:
    # GIVEN an unrecognized status string
    # WHEN _rank is called
    result = _rank("unknown-gibberish")
    # THEN it defaults to 3 (waiting rank)
    assert result == 3


def test_rank_ignores_surrounding_whitespace() -> None:
    # GIVEN a status with extra whitespace
    # WHEN _rank is called
    result = _rank("  error  ")
    # THEN it still returns the correct rank
    assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests: palette.status_color
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,expected_attr",
    [
        pytest.param("error", "ERROR", id="error-red"),
        pytest.param("blocked", "BLOCKED", id="blocked-orange"),
        pytest.param("maintenance", "WARNING", id="maintenance-yellow"),
        pytest.param("waiting", "WARNING", id="waiting-yellow"),
        pytest.param("executing", "WARNING", id="executing-yellow"),
        pytest.param("active", "SUCCESS", id="active-green"),
        pytest.param("idle", "SUCCESS", id="idle-green"),
        pytest.param("started", "SUCCESS", id="started-green"),
    ],
)
def test_status_color_maps_to_correct_palette_attribute(status: str, expected_attr: str) -> None:
    # GIVEN a status string and its expected palette attribute
    # WHEN palette.status_color is called
    result = palette.status_color(status)
    # THEN the returned color matches the palette value
    assert result == getattr(palette, expected_attr)


def test_status_color_unknown_returns_empty_string() -> None:
    # GIVEN an unrecognized status
    # WHEN palette.status_color is called
    result = palette.status_color("something-weird")
    # THEN it returns an empty string (caller renders plain text)
    assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests: _colored_dot
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,expected_symbol",
    [
        pytest.param("error", "✗", id="error-cross"),
        pytest.param("blocked", "✗", id="blocked-cross"),
        pytest.param("maintenance", "⚠", id="maintenance-warning"),
        pytest.param("waiting", "⚠", id="waiting-warning"),
        pytest.param("active", "●", id="active-dot"),
    ],
)
def test_colored_dot_uses_correct_symbol(status: str, expected_symbol: str) -> None:
    # GIVEN a status string
    # WHEN _colored_dot is called
    result = _colored_dot(status)
    # THEN the plain text contains the expected symbol
    assert expected_symbol in result.plain


def test_colored_dot_unknown_status_uses_dot_symbol() -> None:
    # GIVEN an unrecognized status
    # WHEN _colored_dot is called
    result = _colored_dot("unknown")
    # THEN the symbol defaults to a dot
    assert "●" in result.plain


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests: _colored_status
# ─────────────────────────────────────────────────────────────────────────────


def test_colored_status_includes_symbol_and_text() -> None:
    # GIVEN a known status
    # WHEN _colored_status is called
    result = _colored_status("blocked")
    # THEN both the symbol and the status word appear in the plain text
    assert "✗" in result.plain
    assert "blocked" in result.plain


def test_colored_status_empty_string_uses_fallback_dot() -> None:
    # GIVEN an empty status string
    # WHEN _colored_status is called
    result = _colored_status("")
    # THEN the output is just the dot symbol
    assert result.plain == "●"


# ─────────────────────────────────────────────────────────────────────────────
# Pure function tests: _model_worst_status
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "apps, expected",
    [
        pytest.param([], "active", id="empty-list"),
        pytest.param(
            [_app("a", status="active"), _app("b", status="blocked"), _app("c", status="waiting")],
            "blocked",
            id="blocked-beats-waiting",
        ),
        pytest.param(
            [_app("a", status="active"), _app("b", status="idle")], _HEALTHY, id="all-healthy"
        ),
        pytest.param(
            [_app("a", status="blocked"), _app("b", status="error")],
            "error",
            id="error-beats-blocked",
        ),
    ],
)
def test_model_worst_status(apps, expected) -> None:
    # GIVEN a list of apps with various statuses
    # WHEN _model_worst_status is called
    result = _model_worst_status(apps)
    # THEN the result is the expected value (or contained in it for the healthy case)
    if isinstance(expected, (list, tuple, set, frozenset)):
        assert result in expected
    else:
        assert result == expected


# ─────────────────────────────────────────────────────────────────────────────
# HealthView widget tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_view_on_mount_sets_border_titles(pilot) -> None:
    # GIVEN a freshly mounted HealthView
    view = await _mount_health_view(pilot)

    # WHEN we inspect the border titles after mount

    left = view.query_one("#health-left-panel", Vertical)
    right = view.query_one("#health-right-panel", Vertical)

    # THEN both panels have their initial titles
    assert left.border_title == "Models"
    assert right.border_title == "Select a model"


@pytest.mark.asyncio
async def test_health_view_update_populates_models_table(pilot) -> None:
    # GIVEN a mounted HealthView showing all models, with one model and one healthy app
    view = await _mount_health_view(pilot)
    view._show_all = True
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]

    # WHEN update is called
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the models table has one row
    dt = view.query_one("#health-models-table", DataTable)
    assert dt.row_count == 1


@pytest.mark.asyncio
async def test_health_view_models_sorted_worst_first(pilot) -> None:
    # GIVEN a mounted HealthView with models of different severities
    view = await _mount_health_view(pilot)
    models = [_model("healthy", "ctrl"), _model("broken", "ctrl")]
    apps = [
        _app("ok-app", "healthy", "ctrl", "active"),
        _app("bad-app", "broken", "ctrl", "blocked"),
    ]

    # WHEN update is called
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the broken model appears in row 0 (worst first)
    dt = view.query_one("#health-models-table", DataTable)
    row_key_0 = dt.get_row_at(0)
    assert "broken" in str(row_key_0[2])


@pytest.mark.asyncio
async def test_health_view_summary_footer_shows_issue_count(pilot) -> None:
    # GIVEN a mounted HealthView with one blocked app
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "blocked")]

    # WHEN update is called
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the summary label mentions the issue count
    summary = view.query_one("#health-summary", Label)
    assert "1" in str(summary.content)


@pytest.mark.asyncio
async def test_health_view_summary_footer_shows_all_healthy(pilot) -> None:
    # GIVEN a mounted HealthView with only healthy apps
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]

    # WHEN update is called
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the summary label shows the "all healthy" indicator
    summary = view.query_one("#health-summary", Label)
    assert "✓" in str(summary.content)


@pytest.mark.asyncio
async def test_health_view_right_panel_title_shows_issues_on_selection(pilot) -> None:
    # GIVEN a mounted HealthView with a blocked unit

    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]
    units = [_unit("pg/0", "pg", "dev", "ctrl", "blocked", "disk full")]

    # WHEN update is called (auto-selects first model)
    view.update(models, apps, units)
    await pilot.pause()

    # THEN the right panel title reflects the issue count
    right = view.query_one("#health-right-panel", Vertical)
    assert "dev" in right.border_title
    assert "1" in right.border_title


@pytest.mark.asyncio
async def test_health_view_right_panel_title_shows_healthy_when_no_issues(pilot) -> None:
    # GIVEN a mounted HealthView showing all models, with all healthy units

    view = await _mount_health_view(pilot)
    view._show_all = True
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]
    units = [_unit("pg/0", "pg", "dev", "ctrl", "active")]

    # WHEN update is called
    view.update(models, apps, units)
    await pilot.pause()

    # THEN the right panel title shows "all healthy"
    right = view.query_one("#health-right-panel", Vertical)
    assert "healthy" in right.border_title


@pytest.mark.asyncio
async def test_health_view_issues_table_shows_units_for_selected_model(pilot) -> None:
    # GIVEN a mounted HealthView with two models, each with a unit
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl"), _model("prod", "ctrl")]
    apps = [
        _app("pg", "dev", "ctrl", "blocked"),
        _app("mysql", "prod", "ctrl", "active"),
    ]
    units = [
        _unit("pg/0", "pg", "dev", "ctrl", "blocked"),
        _unit("mysql/0", "mysql", "prod", "ctrl", "active"),
    ]

    # WHEN update is called (auto-selects "dev" as worst)
    view.update(models, apps, units)
    await pilot.pause()

    # THEN the issues table only shows units for "dev"
    dt = view.query_one("#health-issues-table", DataTable)
    assert dt.row_count == 1
    row = dt.get_row_at(0)
    assert "pg" in str(row[0])


@pytest.mark.asyncio
async def test_health_view_issues_table_shows_apps_when_no_units(pilot) -> None:
    # GIVEN a model with apps but no units (e.g. pending deploy)
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "waiting")]

    # WHEN update is called with no units
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the issues table shows the app row with "–" as the unit column
    dt = view.query_one("#health-issues-table", DataTable)
    assert dt.row_count == 1
    row = dt.get_row_at(0)
    assert row[1] == "–"


@pytest.mark.asyncio
async def test_health_view_app_message_longer_than_64_chars_is_truncated_in_apps_only_path(
    pilot,
) -> None:
    # GIVEN a model with an app (no units) whose message exceeds 64 chars
    long_msg = "y" * 80
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [
        AppInfo(
            "pg", "dev", "pg", "stable", 1, status="waiting", message=long_msg, controller="ctrl"
        )
    ]

    # WHEN update is called with no units
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the message cell is truncated to 64 chars in the apps-only render path
    dt = view.query_one("#health-issues-table", DataTable)
    row = dt.get_row_at(0)
    assert len(row[3]) <= 64


@pytest.mark.asyncio
async def test_health_view_message_longer_than_64_chars_is_truncated(pilot) -> None:
    # GIVEN a unit with a very long message
    long_msg = "x" * 80
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]
    units = [_unit("pg/0", "pg", "dev", "ctrl", "blocked", long_msg)]

    # WHEN update is called
    view.update(models, apps, units)
    await pilot.pause()

    # THEN the message cell is truncated to 64 chars
    dt = view.query_one("#health-issues-table", DataTable)
    row = dt.get_row_at(0)
    assert len(row[3]) <= 64


@pytest.mark.asyncio
async def test_health_view_row_highlighted_updates_right_panel(pilot) -> None:
    # GIVEN a HealthView with two models

    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl"), _model("prod", "ctrl")]
    apps = [
        _app("pg", "dev", "ctrl", "blocked"),
        _app("mysql", "prod", "ctrl", "active"),
    ]
    view.update(models, apps, [])
    await pilot.pause()

    # WHEN a RowHighlighted event fires for the "prod" row in the models table
    dt = view.query_one("#health-models-table", DataTable)
    event = DataTable.RowHighlighted(dt, cursor_row=1, row_key=MagicMock(value="ctrl/prod"))
    view.on_data_table_row_highlighted(event)
    await pilot.pause()

    # THEN the selected model updates to "prod"
    assert view._selected == ("ctrl", "prod")
    right = view.query_one("#health-right-panel", Vertical)
    assert "prod" in right.border_title


@pytest.mark.asyncio
async def test_health_view_row_highlighted_ignores_issues_table_events(pilot) -> None:
    # GIVEN a HealthView with one model selected
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]
    view.update(models, apps, [])
    await pilot.pause()
    initial_selected = view._selected

    # WHEN a RowHighlighted event fires for the issues table (not the models table)
    issues_dt = view.query_one("#health-issues-table", DataTable)
    event = DataTable.RowHighlighted(issues_dt, cursor_row=0, row_key=MagicMock(value="ctrl/other"))
    view.on_data_table_row_highlighted(event)

    # THEN the selected model is unchanged
    assert view._selected == initial_selected


@pytest.mark.asyncio
async def test_health_view_row_highlighted_ignores_event_with_no_key(pilot) -> None:
    # GIVEN a mounted HealthView
    view = await _mount_health_view(pilot)
    view.update([_model()], [_app("pg")], [])
    await pilot.pause()
    initial_selected = view._selected

    # WHEN a RowHighlighted event fires with a None row_key value
    dt = view.query_one("#health-models-table", DataTable)
    event = DataTable.RowHighlighted(dt, cursor_row=0, row_key=MagicMock(value=None))
    view.on_data_table_row_highlighted(event)

    # THEN the selection is not changed
    assert view._selected == initial_selected


@pytest.mark.asyncio
async def test_health_view_row_selected_posts_model_drill_down(pilot) -> None:
    # GIVEN a HealthView with one model
    view = await _mount_health_view(pilot)
    models = [_model("dev", "ctrl")]
    apps = [_app("pg", "dev", "ctrl", "active")]
    view.update(models, apps, [])
    await pilot.pause()

    received: list[HealthView.ModelDrillDown] = []
    view.app.on_health_view_model_drill_down = lambda m: received.append(m)  # type: ignore[method-assign]

    # WHEN a RowSelected event fires for the "dev" row in the models table
    dt = view.query_one("#health-models-table", DataTable)
    event = DataTable.RowSelected(dt, cursor_row=0, row_key=MagicMock(value="ctrl/dev"))
    with patch.object(view, "post_message") as mock_post:
        view.on_data_table_row_selected(event)

    # THEN post_message was called with a ModelDrillDown for the correct model
    mock_post.assert_called_once()
    msg = mock_post.call_args[0][0]
    assert isinstance(msg, HealthView.ModelDrillDown)
    assert msg.controller == "ctrl"
    assert msg.model == "dev"


@pytest.mark.asyncio
async def test_health_view_row_selected_ignores_issues_table_events(pilot) -> None:
    # GIVEN a HealthView
    view = await _mount_health_view(pilot)
    view.update([_model()], [_app("pg")], [])
    await pilot.pause()

    # WHEN a RowSelected event fires for the issues table (not the models table)
    issues_dt = view.query_one("#health-issues-table", DataTable)
    event = DataTable.RowSelected(issues_dt, cursor_row=0, row_key=MagicMock(value="ctrl/dev"))
    with patch.object(view, "post_message") as mock_post:
        view.on_data_table_row_selected(event)

    # THEN post_message is NOT called
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_health_view_row_selected_ignores_event_with_no_key(pilot) -> None:
    # GIVEN a HealthView
    view = await _mount_health_view(pilot)
    view.update([_model()], [_app("pg")], [])
    await pilot.pause()

    # WHEN a RowSelected event fires with a None row_key value
    dt = view.query_one("#health-models-table", DataTable)
    event = DataTable.RowSelected(dt, cursor_row=0, row_key=MagicMock(value=None))
    with patch.object(view, "post_message") as mock_post:
        view.on_data_table_row_selected(event)

    # THEN post_message is NOT called
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_health_view_empty_update_renders_no_rows(pilot) -> None:
    # GIVEN a mounted HealthView
    view = await _mount_health_view(pilot)

    # WHEN update is called with empty lists
    view.update([], [], [])
    await pilot.pause()

    # THEN both tables have zero rows
    assert view.query_one("#health-models-table", DataTable).row_count == 0
    assert view.query_one("#health-issues-table", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_health_view_preserves_selection_on_re_render(pilot) -> None:
    # GIVEN a HealthView showing all models, with "prod" manually selected
    view = await _mount_health_view(pilot)
    view._show_all = True
    models = [_model("dev", "ctrl"), _model("prod", "ctrl")]
    apps = [
        _app("pg", "dev", "ctrl", "blocked"),
        _app("mysql", "prod", "ctrl", "active"),
    ]
    view.update(models, apps, [])
    await pilot.pause()
    view._selected = ("ctrl", "prod")

    # WHEN update is called again with the same data
    view.update(models, apps, [])
    await pilot.pause()

    # THEN the selection is preserved
    assert view._selected == ("ctrl", "prod")


# ─────────────────────────────────────────────────────────────────────────────
# MainScreen integration: on_health_view_model_drill_down
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_drill_down_switches_to_status_tab_and_sets_filter(pilot) -> None:
    # GIVEN apps in two models on two different controllers
    screen = pilot.app.screen
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1, controller="ctrl-a"),
        AppInfo("mysql", "prod", "mysql", "8/stable", 1, controller="ctrl-b"),
    ]
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get_status_details.return_value = ([], [], [])

    with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
        # WHEN on_health_view_model_drill_down is called for ctrl-a/dev
        screen.on_health_view_model_drill_down(HealthView.ModelDrillDown("ctrl-a", "dev"))
        await pilot.pause()
        await pilot.pause()

    # THEN the tab switches to Status and the correct model is filtered
    assert screen.query_one(TabbedContent).active == "tab-status"
    assert screen._selected_controller == "ctrl-a"
    assert screen._selected_model == "dev"
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-apps-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_health_drill_down_refreshes_header(pilot) -> None:
    # GIVEN a main screen
    screen = pilot.app.screen
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get_status_details.return_value = ([], [], [])

    with patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client):
        with patch.object(screen, "_refresh_header") as mock_refresh:
            # WHEN on_health_view_model_drill_down is called
            screen.on_health_view_model_drill_down(HealthView.ModelDrillDown("ctrl", "dev"))
            await pilot.pause()

    # THEN the header is refreshed
    mock_refresh.assert_called()


@pytest.mark.asyncio
async def test_apps_updated_populates_health_view_when_health_tab_active(pilot) -> None:
    # GIVEN the Health tab is active
    screen = pilot.app.screen
    screen.action_switch_tab("tab-health")
    await pilot.pause()
    screen._all_models = [_model("dev", "ctrl")]

    # WHEN an AppsUpdated message is received
    from jujumate.client.watcher import AppsUpdated

    screen.on_apps_updated(AppsUpdated(apps=[_app("pg", "dev", "ctrl", "blocked")]))
    await pilot.pause()

    # THEN the health view models table is populated
    hv = screen.query_one("#health-view", HealthView)
    assert hv.query_one("#health-models-table", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_apps_updated_does_not_update_health_view_when_status_tab_active(pilot) -> None:
    # GIVEN the Status tab is active (not Health)
    screen = pilot.app.screen
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    screen._all_models = [_model("dev", "ctrl")]

    # WHEN an AppsUpdated message is received
    from jujumate.client.watcher import AppsUpdated

    screen.on_apps_updated(AppsUpdated(apps=[_app("pg", "dev", "ctrl", "blocked")]))
    await pilot.pause()

    # THEN the health view models table is still empty (was not updated)
    hv = screen.query_one("#health-view", HealthView)
    assert hv.query_one("#health-models-table", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_tab_switch_to_health_renders_with_cached_data(pilot) -> None:
    # GIVEN some cached data in the screen
    screen = pilot.app.screen
    screen._all_models = [_model("dev", "ctrl")]
    screen._all_apps = [_app("pg", "dev", "ctrl", "blocked")]

    # WHEN on_tabbed_content_tab_activated fires for "tab-health"
    tab = MagicMock()
    tab.id = "tab-health"
    event = MagicMock()
    event.tab = tab
    screen.on_tabbed_content_tab_activated(event)
    await pilot.pause()

    # THEN the health view renders the cached models immediately
    hv = screen.query_one("#health-view", HealthView)
    assert hv.query_one("#health-models-table", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_tab_switch_to_status_moves_focus_to_apps_table(pilot) -> None:
    # GIVEN the Health tab is active
    screen = pilot.app.screen
    screen.action_switch_tab("tab-health")
    await pilot.pause()

    # WHEN the user switches to the Status tab
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    await pilot.pause()

    # THEN focus lands on the apps DataTable within Status
    focused = screen.focused
    assert focused is not None
    assert isinstance(focused, DataTable)


# ─────────────────────────────────────────────────────────────────────────────
# action_toggle_filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_toggle_filter_shows_all_models(pilot) -> None:
    # GIVEN a HealthView with one unhealthy and one healthy model (default: unhealthy-only)
    view = await _mount_health_view(pilot)
    models = [_model("broken", "ctrl"), _model("healthy", "ctrl")]
    apps = [
        _app("pg", "broken", "ctrl", "blocked"),
        _app("ok", "healthy", "ctrl", "active"),
    ]
    view.update(models, apps, [])
    await pilot.pause()
    dt = view.query_one("#health-models-table", DataTable)
    assert dt.row_count == 1  # only broken shown by default

    # WHEN action_toggle_filter is called
    view.action_toggle_filter()
    await pilot.pause()

    # THEN all models are shown
    assert dt.row_count == 2
    assert view._show_all is True


@pytest.mark.asyncio
async def test_action_toggle_filter_back_to_unhealthy_only(pilot) -> None:
    # GIVEN a HealthView showing all models (_show_all=True)
    view = await _mount_health_view(pilot)
    view._show_all = True
    models = [_model("broken", "ctrl"), _model("healthy", "ctrl")]
    apps = [
        _app("pg", "broken", "ctrl", "blocked"),
        _app("ok", "healthy", "ctrl", "active"),
    ]
    view.update(models, apps, [])
    await pilot.pause()
    dt = view.query_one("#health-models-table", DataTable)
    assert dt.row_count == 2

    # WHEN action_toggle_filter is called again
    view.action_toggle_filter()
    await pilot.pause()

    # THEN only unhealthy models are shown
    assert dt.row_count == 1
    assert view._show_all is False
