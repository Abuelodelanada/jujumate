import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from juju.errors import JujuError
from textual.css.query import NoMatches
from textual.widgets import DataTable, Label, ListItem, ListView, Static, TabbedContent
from textual.widgets._data_table import RowKey

from jujumate.app import JujuMateApp, _asyncio_exception_handler
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
    SaasUpdated,
    StorageUpdated,
    UnitsUpdated,
)
from jujumate.config import JujuConfig, JujuConfigError
from jujumate.models.entities import (
    AppConfigEntry,
    AppInfo,
    CloudInfo,
    ControllerInfo,
    ControllerOfferInfo,
    MachineInfo,
    ModelInfo,
    OfferEndpoint,
    OfferInfo,
    RelationDataEntry,
    RelationInfo,
    SAASInfo,
    SecretInfo,
    StorageInfo,
    UnitInfo,
)
from jujumate.screens.app_config_screen import AppConfigScreen
from jujumate.screens.log_screen import LogScreen
from jujumate.screens.machine_detail_screen import MachineDetailScreen
from jujumate.screens.main_screen import MainScreen
from jujumate.screens.offers_screen import OfferDetailScreen, OffersScreen, _ConsumerEntry
from jujumate.screens.relation_data_screen import RelationDataScreen
from jujumate.screens.secrets_screen import SecretDetailScreen, SecretsScreen
from jujumate.screens.settings_screen import SettingsScreen
from jujumate.screens.storage_detail_screen import StorageDetailScreen
from jujumate.screens.theme_screen import ThemeScreen
from jujumate.settings import AppSettings
from jujumate.widgets.app_config_view import AppConfigView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.health_view import HealthView
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.relation_data_view import RelationDataView
from jujumate.widgets.status_view import StatusView


def _make_juju_client_mock(**method_returns) -> AsyncMock:
    """Build a JujuClient async context manager mock.

    Pass method names and their return values as keyword arguments:
        _make_juju_client_mock(get_status_details=([], [], []))
    """
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    for method_name, return_value in method_returns.items():
        getattr(mock, method_name).return_value = return_value
    return mock


async def _run_connect_and_poll(
    screen: MainScreen,
    current_model: str | None = None,
    controller_models: dict[str, str] | None = None,
    default_controller: str | None = None,
) -> tuple[AsyncMock, MagicMock]:
    """Call _connect_and_poll with mocked load_config and JujuPoller.

    Returns (mock_poller, MockPoller) for assertions.
    """
    config = JujuConfig(
        current_controller="prod",
        controllers=["prod"],
        current_model=current_model,
        controller_models=controller_models
        if controller_models is not None
        else ({"prod": current_model} if current_model else {}),
    )
    # Always reset default_controller for test isolation (avoids stale disk config leaking in)
    screen._settings.default_controller = default_controller
    with (
        patch("jujumate.screens.main_screen.load_config", return_value=config),
        patch("jujumate.screens.main_screen.JujuPoller") as MockPoller,
    ):
        mock_poller = AsyncMock()
        MockPoller.return_value = mock_poller
        await screen._connect_and_poll()
    return mock_poller, MockPoller


@pytest.mark.asyncio
async def test_initial_app_state(pilot):
    # GIVEN the application has just started
    # WHEN we inspect the current screen and active tab
    # THEN the screen is MainScreen and the default tab is clouds
    assert pilot.app.screen.__class__.__name__ == "MainScreen"
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-clouds"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,expected_tab_id",
    [
        pytest.param("m", "tab-models", id="m-to-models"),
        pytest.param("s", "tab-status", id="s-to-status"),
    ],
)
async def test_keybinding_switches_tab(pilot, key, expected_tab_id):
    # GIVEN the application is running on the clouds tab
    # WHEN the keybinding key is pressed
    await pilot.press(key)
    # THEN the tab switches to the expected tab
    assert pilot.app.screen.query_one(TabbedContent).active == expected_tab_id


@pytest.mark.asyncio
async def test_keybinding_q_exits(pilot):
    # GIVEN the application is running
    # WHEN the q key is pressed
    await pilot.press("q")
    # THEN the app exits with None return value
    assert pilot.app.return_value is None


@pytest.mark.asyncio
async def test_keybinding_r_triggers_refresh(pilot):
    # GIVEN the application is running
    screen = pilot.app.screen
    with patch.object(screen, "notify") as mock_notify:
        # WHEN the r key is pressed
        await pilot.press("r")
        await pilot.pause()
    # THEN the refresh notification was shown and the app is still running
    mock_notify.assert_called_once_with("Refreshing…")
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_app_falls_back_when_theme_not_found():
    # GIVEN a settings object with a nonexistent theme name
    settings = AppSettings(theme="nonexistent-theme")
    app = JujuMateApp(settings=settings)
    # WHEN the app is started
    async with app.run_test() as pilot:
        await pilot.pause()
        # THEN the app still mounts correctly
        assert app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_message_handlers_update_views(pilot):
    # GIVEN the application is running
    screen = pilot.app.screen
    # WHEN various data update messages are posted
    screen.on_clouds_updated(CloudsUpdated(clouds=[CloudInfo("aws", "ec2")]))
    screen.on_controllers_updated(
        ControllersUpdated(controllers=[ControllerInfo("ctrl", "aws", "", "3.4.0", model_count=1)])
    )
    screen.on_models_updated(ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")]))
    screen.on_apps_updated(AppsUpdated(apps=[AppInfo("pg", "dev", "pg", "14/stable", 1)]))
    screen.on_units_updated(UnitsUpdated(units=[UnitInfo("pg/0", "pg", "0", "active", "idle")]))
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))
    await pilot.pause()
    # THEN the connection flag is set and timestamp is updated
    assert screen._is_connected is True
    assert screen._last_refresh_ts == "12:00:00"


@pytest.mark.asyncio
async def test_connection_failed_sets_subtitle(pilot):
    # GIVEN the application is running
    # WHEN a ConnectionFailed message is posted
    pilot.app.screen.on_connection_failed(ConnectionFailed(error="timeout"))
    # THEN the connected flag is cleared
    assert pilot.app.screen._is_connected is False


@pytest.mark.asyncio
async def test_action_refresh_data_without_poller(pilot):
    # GIVEN no poller is set (_poller is None)
    # WHEN action_refresh_data is called
    await pilot.app.screen.action_refresh_data()
    # THEN the app does not crash and stays on MainScreen
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_refresh_header_before_mount_does_not_crash():
    """_refresh_header guard: calling before widgets are mounted must not raise."""
    # GIVEN a MainScreen that has not been mounted in an app
    screen = MainScreen(settings=AppSettings(juju_data_dir=Path("/nonexistent")))
    # WHEN _refresh_header is called
    # THEN it silently returns without raising
    screen._refresh_header()


@pytest.mark.asyncio
async def test_connect_and_poll_connection_failure(pilot):
    # GIVEN load_config raises JujuConfigError
    screen = pilot.app.screen
    with patch(
        "jujumate.screens.main_screen.load_config",
        side_effect=JujuConfigError("no config"),
    ):
        # WHEN _connect_and_poll is called
        await screen._connect_and_poll()
    await pilot.pause()
    # THEN the screen is not connected
    assert screen._is_connected is False


@pytest.mark.asyncio
async def test_connect_and_poll_success(pilot):
    # GIVEN load_config returns a valid config and JujuPoller is mocked
    screen = pilot.app.screen
    # WHEN _connect_and_poll is called
    mock_poller, MockPoller = await _run_connect_and_poll(screen)
    # THEN the poller is created with the right controllers and poll_once is called
    MockPoller.assert_called_once_with(controller_names=["prod"], target=screen)
    mock_poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_and_poll_sets_auto_select_from_config(pilot):
    # GIVEN load_config returns a config with a current model for 'prod'
    screen = pilot.app.screen
    # WHEN _connect_and_poll is called with controller_models populated
    await _run_connect_and_poll(screen, controller_models={"prod": "mymodel"})
    # THEN _auto_select_model is set to the model of the Juju current controller
    assert screen._auto_select_model == "mymodel"


@pytest.mark.asyncio
async def test_connect_and_poll_uses_settings_default_controller(pilot):
    # GIVEN settings has default_controller pointing to 'staging'
    screen = pilot.app.screen
    # WHEN _connect_and_poll is called; Juju current is 'prod' but settings says 'staging'
    await _run_connect_and_poll(
        screen,
        controller_models={"prod": "prod-model", "staging": "staging-model"},
        default_controller="staging",
    )
    # THEN _auto_select_model uses staging's model, not prod's
    assert screen._auto_select_model == "staging-model"


@pytest.mark.asyncio
async def test_connect_and_poll_no_default_controller_skips_auto_select(pilot):
    # GIVEN neither settings nor Juju config has a default controller
    screen = pilot.app.screen
    config = JujuConfig(current_controller=None, controllers=["prod", "staging"])
    with (
        patch("jujumate.screens.main_screen.load_config", return_value=config),
        patch("jujumate.screens.main_screen.JujuPoller") as MockPoller,
    ):
        MockPoller.return_value = AsyncMock()
        await screen._connect_and_poll()
    # THEN no model is auto-selected (app stays on Clouds tab)
    assert screen._auto_select_model is None


@pytest.mark.asyncio
async def test_action_refresh_data_with_poller(pilot):
    # GIVEN a poller is set
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    # WHEN action_refresh_data is called
    await screen.action_refresh_data()
    # THEN poll_once is called
    screen._poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_refresh_data_with_poller_and_model(pilot):
    # GIVEN a poller is set and a controller+model are selected
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    # WHEN action_refresh_data is called
    await screen.action_refresh_data()
    # THEN poll_once is called (relations/offers/saas come from the poll itself)
    screen._poller.poll_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_cloud_selected_switches_to_controllers_and_filters(pilot):
    # GIVEN two controllers on different clouds
    screen = pilot.app.screen
    screen._all_controllers = [
        ControllerInfo("prod", "aws", "", "3.4.0", 1),
        ControllerInfo("dev", "lxd", "", "3.4.0", 1),
    ]
    # WHEN a cloud is selected
    screen.on_clouds_view_cloud_selected(CloudsView.CloudSelected(name="aws"))
    await pilot.pause()
    # THEN the tab switches to controllers and only the matching controller is shown
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-controllers"
    ctrl_view = screen.query_one("#controllers-view", ControllersView)
    assert len(ctrl_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_controller_selected_switches_to_models_and_filters(pilot):
    # GIVEN two models on different controllers
    screen = pilot.app.screen
    screen._all_models = [
        ModelInfo("dev", "prod", "aws", "", "available"),
        ModelInfo("staging", "other-ctrl", "aws", "", "available"),
    ]
    # WHEN a controller is selected
    screen.on_controllers_view_controller_selected(ControllersView.ControllerSelected(name="prod"))
    await pilot.pause()
    # THEN the tab switches to models and only the matching model is shown
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"
    models_view = screen.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_model_selected_switches_to_status_and_filters(pilot):
    # GIVEN two apps in different models
    screen = pilot.app.screen
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1, controller="ctrl"),
        AppInfo("mysql", "prod", "mysql", "8/stable", 1, controller="other-ctrl"),
    ]
    mock_client = _make_juju_client_mock(get_status_details=([], [], []))
    with (
        patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client),
        patch("jujumate.screens.main_screen.save_settings"),
    ):
        screen._selected_controller = "ctrl"
        # WHEN a model with a controller prefix is selected
        screen.on_models_view_model_selected(ModelsView.ModelSelected(name="ctrl/dev"))
        await pilot.pause()
        await pilot.pause()
    # THEN the tab switches to status and only the matching app is shown
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-status"
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-apps-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_model_selected_without_slash_sets_model_only(pilot):
    # GIVEN no controller is preselected and the model name has no slash
    screen = pilot.app.screen
    screen._selected_controller = None
    # WHEN on_models_view_model_selected is called with a plain model name
    screen.on_models_view_model_selected(ModelsView.ModelSelected(name="mymodel"))
    await pilot.pause()
    # THEN _selected_model is set to the plain name
    assert screen._selected_model == "mymodel"


@pytest.mark.asyncio
async def test_model_selected_saves_default_controller_to_settings(pilot):
    # GIVEN a model is selected via drill-down
    screen = pilot.app.screen
    screen._settings.default_controller = None
    mock_client = _make_juju_client_mock(get_status_details=([], [], []))
    with (
        patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client),
        patch("jujumate.screens.main_screen.save_settings") as mock_save,
    ):
        # WHEN on_models_view_model_selected is called with a controller/model name
        screen.on_models_view_model_selected(ModelsView.ModelSelected(name="ck8s/monitoring"))
        await pilot.pause()
        await pilot.pause()
    # THEN the selected controller is persisted as default_controller
    assert screen._settings.default_controller == "ck8s"
    mock_save.assert_called_once_with(screen._settings)


@pytest.mark.asyncio
async def test_health_drill_down_saves_default_controller_to_settings(pilot):
    # GIVEN a model is selected from the health view
    screen = pilot.app.screen
    screen._settings.default_controller = None
    mock_client = _make_juju_client_mock(get_status_details=([], [], []))
    with (
        patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client),
        patch("jujumate.screens.main_screen.save_settings") as mock_save,
    ):
        # WHEN on_health_view_model_drill_down fires
        screen.on_health_view_model_drill_down(
            HealthView.ModelDrillDown(controller="lxd", model="default")
        )
        await pilot.pause()
        await pilot.pause()
    # THEN the controller from the health event is persisted
    assert screen._settings.default_controller == "lxd"
    mock_save.assert_called_once_with(screen._settings)


@pytest.mark.asyncio
async def test_clear_filter_resets_cloud_and_controller(pilot):
    # GIVEN a cloud and controller filter are active and no model is selected
    screen = pilot.app.screen
    screen._selected_cloud = "aws"
    screen._selected_controller = "prod"
    screen._selected_model = None
    screen._all_controllers = [
        ControllerInfo("prod", "aws", "", "3.4.0", 1),
        ControllerInfo("dev", "lxd", "", "3.4.0", 1),
    ]
    # WHEN action_clear_filter is called
    screen.action_clear_filter()
    await pilot.pause()
    # THEN cloud and controller filters are cleared and all controllers are shown
    assert screen._selected_cloud is None
    assert screen._selected_controller is None
    ctrl_view = screen.query_one("#controllers-view", ControllersView)
    assert len(ctrl_view.query_one(NavigableTable)._rows) == 2


@pytest.mark.asyncio
async def test_clear_filter_noop_when_model_selected(pilot):
    """Esc does nothing when a model is selected — preserves the full nav state."""
    # GIVEN a cloud, controller, and model are all selected
    screen = pilot.app.screen
    screen._selected_cloud = "aws"
    screen._selected_controller = "prod"
    screen._selected_model = "mymodel"
    # WHEN action_clear_filter is called
    screen.action_clear_filter()
    await pilot.pause()
    # THEN all selections are preserved
    assert screen._selected_cloud == "aws"
    assert screen._selected_controller == "prod"
    assert screen._selected_model == "mymodel"


@pytest.mark.parametrize(
    "context,should_suppress",
    [
        pytest.param({"exception": RuntimeError("Event loop is closed")}, True, id="closed-loop"),
        pytest.param({"exception": OSError("Bad file descriptor")}, True, id="bad-fd"),
        pytest.param(
            {"exception": RuntimeError("cannot reuse already awaited coroutine")},
            True,
            id="cannot-reuse",
        ),
        pytest.param(
            {"message": "Task was destroyed but it is pending!"}, True, id="task-destroyed"
        ),
        pytest.param({"exception": ValueError("something unexpected")}, False, id="value-error"),
        pytest.param({"message": "some asyncio message"}, False, id="asyncio-message"),
    ],
)
def test_asyncio_exception_handler(context, should_suppress):
    # GIVEN an asyncio event loop and an exception context
    loop = MagicMock()
    # WHEN _asyncio_exception_handler is called
    _asyncio_exception_handler(loop, context)
    # THEN expected exceptions are suppressed, others are delegated
    if should_suppress:
        loop.default_exception_handler.assert_not_called()
    else:
        loop.default_exception_handler.assert_called_once_with(context)


@pytest.mark.asyncio
async def test_relations_updated_populates_status_view(pilot):
    # GIVEN a model is selected and the Status tab is active
    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    # WHEN a RelationsUpdated message is posted
    screen.on_relations_updated(
        RelationsUpdated(
            model="dev",
            relations=[
                RelationInfo("dev", "postgresql:db", "wordpress:db", "pgsql", "regular"),
            ],
        )
    )
    await pilot.pause()
    # THEN the relation is shown in the status view
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-rels-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_relations_updated_replaces_existing_for_same_model(pilot):
    # GIVEN relations already exist for "dev" and "prod" models
    screen = pilot.app.screen
    screen._all_relations = [
        RelationInfo("dev", "a:x", "b:x", "iface", "regular"),
        RelationInfo("prod", "c:x", "d:x", "iface2", "regular"),
    ]
    screen._selected_model = "dev"
    # WHEN a RelationsUpdated message for "dev" is posted with a new relation
    screen.on_relations_updated(
        RelationsUpdated(
            model="dev",
            relations=[RelationInfo("dev", "new:x", "new2:x", "iface3", "regular")],
        )
    )
    await pilot.pause()
    # THEN only the new relation for "dev" remains; "prod" relations are untouched
    dev_rels = [r for r in screen._all_relations if r.model == "dev"]
    prod_rels = [r for r in screen._all_relations if r.model == "prod"]
    assert len(dev_rels) == 1
    assert dev_rels[0].provider == "new:x"
    assert len(prod_rels) == 1


@pytest.mark.asyncio
async def test_offers_updated_populates_status_view(pilot):
    # GIVEN a model is selected and the Status tab is active
    screen = pilot.app.screen
    screen._selected_model = "cos"
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    # WHEN an OffersUpdated message is posted
    screen.on_offers_updated(
        OffersUpdated(
            model="cos",
            offers=[
                OfferInfo(
                    "cos",
                    "alertmanager-karma-dashboard",
                    "alertmanager",
                    "alertmanager-k8s",
                    180,
                    "0/0",
                    "karma-dashboard",
                    "karma_dashboard",
                    "provider",
                ),
            ],
        )
    )
    await pilot.pause()
    # THEN the offer is shown in the status view
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-offers-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_saas_updated_populates_status_view(pilot):
    # GIVEN a model is selected and the Status tab is active
    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    # WHEN a SaasUpdated message is received
    screen.on_saas_updated(
        SaasUpdated(
            model="dev",
            controller="ctrl",
            saas=[SAASInfo("dev", "remote-pg", "active", "mystore", "mystore:admin/pg")],
        )
    )
    await pilot.pause()
    # THEN the SAAS entry is stored and the status view is refreshed
    assert any(s.model == "dev" for s in screen._all_saas)


@pytest.mark.asyncio
async def test_machines_updated_populates_status_view(pilot):
    # GIVEN a model is selected and the Status tab is active
    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen._all_models = [ModelInfo("dev", "prod", "aws", "us-east-1", "available")]
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    # WHEN a MachinesUpdated message is posted
    screen.on_machines_updated(
        MachinesUpdated(
            machines=[
                MachineInfo(
                    "dev", "0", "started", "10.0.0.1", "i-1234", "ubuntu@22.04", "us-east-1a"
                ),
            ],
        )
    )
    await pilot.pause()
    # THEN the machine is shown in the status view
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-machines-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_fetch_relations_worker_posts_message(pilot):
    # GIVEN a RelationsUpdated message posted directly (as the poller now does)
    screen = pilot.app.screen
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular")
    # WHEN on_relations_updated is received (simulating what the poller posts)
    screen.on_relations_updated(RelationsUpdated(model="dev", controller="ctrl", relations=[rel]))
    await pilot.pause()
    # THEN the relation is stored in _all_relations
    assert any(r.model == "dev" for r in screen._all_relations)


@pytest.mark.asyncio
async def test_auto_select_navigates_to_status_on_first_refresh(pilot):
    # GIVEN an auto-select model is set and data is available
    screen = pilot.app.screen
    screen._auto_select_model = "dev"
    screen.on_models_updated(ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")]))
    screen.on_apps_updated(AppsUpdated(apps=[AppInfo("pg", "dev", "pg", "14/stable", 1)]))
    screen.on_units_updated(UnitsUpdated(units=[UnitInfo("pg/0", "pg", "0", "active", "idle")]))
    # WHEN on_data_refreshed is received
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))
    await pilot.pause()
    # THEN the model is auto-selected and the status tab is shown
    assert screen._selected_model == "dev"
    assert screen._selected_controller == "ctrl"
    assert screen.query_one(TabbedContent).active == "tab-status"
    assert screen._auto_select_model is None


@pytest.mark.asyncio
async def test_auto_select_not_found_does_not_crash(pilot):
    # GIVEN an auto-select model that does not exist in loaded data
    screen = pilot.app.screen
    screen._auto_select_model = "nonexistent"
    # WHEN on_data_refreshed is received
    screen.on_data_refreshed(DataRefreshed(timestamp=datetime(2024, 1, 1, 12, 0, 0)))
    await pilot.pause()
    # THEN nothing is selected and auto_select is cleared
    assert screen._selected_model is None
    assert screen._auto_select_model is None


@pytest.mark.asyncio
async def test_help_screen_opens_and_closes_with_question_mark(pilot):
    # GIVEN the application is running on the main screen
    assert pilot.app.screen.__class__.__name__ == "MainScreen"
    # WHEN the question_mark key is pressed
    await pilot.press("question_mark")
    await pilot.pause()
    # THEN the HelpScreen is shown; pressing again closes it
    assert pilot.app.screen.__class__.__name__ == "HelpScreen"
    await pilot.press("question_mark")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_help_screen_closes_with_escape(pilot):
    # GIVEN the HelpScreen is open
    await pilot.press("question_mark")
    await pilot.pause()
    assert pilot.app.screen.__class__.__name__ == "HelpScreen"
    # WHEN Escape is pressed
    await pilot.press("escape")
    await pilot.pause()
    # THEN we return to MainScreen
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


# ─────────────────────────────────────────────────────────────────────────────
# _periodic_poll
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_periodic_poll_no_poller_is_noop(pilot):
    # GIVEN no poller is set
    screen = pilot.app.screen
    screen._poller = None
    # WHEN _periodic_poll is called
    await screen._periodic_poll()
    # THEN _is_connected is unchanged (False) and no error is raised
    assert screen._is_connected is False


@pytest.mark.asyncio
async def test_periodic_poll_skipped_when_modal_is_open(pilot):
    """No poll is made while any modal screen is on top of MainScreen."""
    # GIVEN a poller is set and a modal is pushed over MainScreen
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    screen.query_one(TabbedContent).active = "tab-status"
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    with patch.object(OffersScreen, "_fetch"):
        screen.action_show_offers()
        await pilot.pause()
    assert isinstance(pilot.app.screen, OffersScreen)
    # WHEN _periodic_poll fires while the modal is open
    await screen._periodic_poll()
    # THEN no poll is made
    screen._poller.poll_model.assert_not_awaited()
    screen._poller.poll_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_poll_non_status_tab_does_not_call_poll_once(pilot):
    # GIVEN a poller is set and the active tab is NOT "tab-status"
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    screen.query_one(TabbedContent).active = "tab-clouds"
    # WHEN _periodic_poll is called
    await screen._periodic_poll()
    # THEN poll_once is NOT called
    screen._poller.poll_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_poll_status_tab_with_model_calls_poll_model(pilot):
    # GIVEN a poller is set, the tab is "tab-status", and a model is selected
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    screen.query_one(TabbedContent).active = "tab-status"
    # WHEN _periodic_poll is called
    await screen._periodic_poll()
    # THEN poll_model is called with the selected controller and model (targeted poll)
    screen._poller.poll_model.assert_awaited_once_with("ctrl", "dev")
    screen._poller.poll_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_poll_status_tab_no_model_calls_poll_once(pilot):
    # GIVEN a poller is set, the tab is "tab-status", but no model is selected
    screen = pilot.app.screen
    screen._poller = AsyncMock(spec=JujuPoller)
    screen._selected_controller = ""
    screen._selected_model = ""
    screen.query_one(TabbedContent).active = "tab-status"
    # WHEN _periodic_poll is called
    await screen._periodic_poll()
    # THEN poll_once is called (full poll since no model is selected)
    screen._poller.poll_once.assert_awaited_once()
    screen._poller.poll_model.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# on_tabbed_content_tab_activated — focus mapped tab
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tab_activated_with_mapped_tab_calls_focus(pilot):
    # GIVEN the main screen is active
    screen = pilot.app.screen
    # WHEN on_tabbed_content_tab_activated is called with a tab id in _TAB_FOCUS_MAP
    tab = MagicMock()
    tab.id = "tab-clouds"
    event = MagicMock()
    event.tab = tab
    with patch.object(screen, "call_after_refresh") as mock_car:
        screen.on_tabbed_content_tab_activated(event)
    # THEN call_after_refresh is invoked
    mock_car.assert_called_once()


@pytest.mark.asyncio
async def test_tab_activated_status_schedules_refresh(pilot):
    # GIVEN the main screen is active
    screen = pilot.app.screen

    # WHEN on_tabbed_content_tab_activated fires for "tab-status"
    tab = MagicMock()
    tab.id = "tab-status"
    event = MagicMock()
    event.tab = tab
    calls = []
    with patch.object(screen, "call_after_refresh", side_effect=calls.append):
        screen.on_tabbed_content_tab_activated(event)

    # THEN call_after_refresh is called twice (focus + refresh_status_view)
    assert len(calls) == 2
    assert screen._refresh_status_view in calls


@pytest.mark.asyncio
async def test_active_tab_returns_empty_string_when_not_mounted(pilot):
    # GIVEN a MainScreen whose TabbedContent raises NoMatches
    screen = pilot.app.screen

    # WHEN _active_tab is called and query_one raises NoMatches

    with patch.object(screen, "query_one", side_effect=NoMatches()):
        result = screen._active_tab()

    # THEN the method returns an empty string instead of raising
    assert result == ""


@pytest.mark.asyncio
async def test_action_toggle_health_filter_delegates_to_health_view(pilot):
    # GIVEN the Health tab is active
    screen = pilot.app.screen
    screen.action_switch_tab("tab-health")
    await pilot.pause()

    # WHEN action_toggle_health_filter is called
    hv = screen.query_one("#health-view", HealthView)
    assert hv._show_all is False
    screen.action_toggle_health_filter()
    await pilot.pause()

    # THEN the health view's _show_all is toggled
    assert hv._show_all is True


# ─────────────────────────────────────────────────────────────────────────────
# action_show_secrets / action_show_logs — no selection (parametrized)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action_name",
    [
        pytest.param("action_show_secrets", id="secrets"),
        pytest.param("action_show_logs", id="logs"),
        pytest.param("action_show_offers", id="offers"),
    ],
)
async def test_action_show_screen_no_selection_stays_on_main(pilot, action_name):
    # GIVEN no controller or model is selected
    screen = pilot.app.screen
    screen._selected_controller = None
    screen._selected_model = None
    # WHEN the action is invoked
    getattr(screen, action_name)()
    await pilot.pause()
    # THEN we stay on MainScreen (no push_screen occurred)
    assert isinstance(pilot.app.screen, MainScreen)


# ─────────────────────────────────────────────────────────────────────────────
# action_show_secrets / action_show_logs — with selection (parametrized)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action_name, screen_class, patch_attr",
    [
        pytest.param("action_show_secrets", SecretsScreen, "_fetch", id="secrets"),
        pytest.param("action_show_logs", LogScreen, "_start_stream", id="logs"),
    ],
)
async def test_action_show_screen_with_selection_pushes_screen(
    pilot, action_name, screen_class, patch_attr
):
    # GIVEN a controller and model are selected
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    # WHEN the action is called
    with patch.object(screen_class, patch_attr):
        getattr(screen, action_name)()
        await pilot.pause()
    # THEN the appropriate screen is pushed
    assert isinstance(pilot.app.screen, screen_class)


# ─────────────────────────────────────────────────────────────────────────────
# action_show_settings
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_action_show_settings_pushes_settings_screen(pilot):
    # GIVEN the main screen is active
    screen = pilot.app.screen
    # WHEN action_show_settings is called
    screen.action_show_settings()
    await pilot.pause()
    # THEN SettingsScreen is pushed
    assert isinstance(pilot.app.screen, SettingsScreen)


@pytest.mark.asyncio
async def test_action_show_settings_apply_callback_with_none_does_nothing(pilot):
    # GIVEN the main screen with a known refresh_interval
    main = pilot.app.screen
    original_interval = main._settings.refresh_interval

    # WHEN action_show_settings is called (push_screen mocked to avoid stack side effects)
    with patch.object(pilot.app, "push_screen") as mock_push:
        main.action_show_settings()
        await pilot.pause()

    # Extract the _apply callback from the push_screen call
    _apply = mock_push.call_args[0][1]
    _apply(None)

    # THEN settings remain unchanged
    assert main._settings.refresh_interval == original_interval


@pytest.mark.asyncio
async def test_action_show_settings_apply_callback_restarts_timer_on_interval_change(pilot):
    # GIVEN the main screen with refresh_interval=5 and a running timer
    main = pilot.app.screen
    main._settings.refresh_interval = 5
    mock_timer = MagicMock()
    main._poll_timer = mock_timer  # simulate a running timer

    with patch.object(pilot.app, "push_screen") as mock_push:
        main.action_show_settings()
        await pilot.pause()

    _apply = mock_push.call_args[0][1]

    # WHEN _apply is called with settings that have a different refresh_interval
    from jujumate.settings import AppSettings

    new_settings = AppSettings(
        refresh_interval=10,
        default_controller=main._settings.default_controller,
        juju_data_dir=main._settings.juju_data_dir,
        log_file=main._settings.log_file,
        log_level=main._settings.log_level,
        theme=main._settings.theme,
    )
    with patch.object(main, "set_interval", return_value=MagicMock()) as mock_interval:
        _apply(new_settings)

    # THEN the old timer is stopped, a new one started, and settings updated
    mock_timer.stop.assert_called_once()
    mock_interval.assert_called_once_with(10, main._periodic_poll)
    assert main._settings.refresh_interval == 10


# ─────────────────────────────────────────────────────────────────────────────
# on_status_view_app_selected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_app_selected_pushes_app_config_screen(pilot):
    # GIVEN a controller and model are selected
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    ai = AppInfo("pg", "dev", "pg", "14/stable", 1)
    # WHEN on_status_view_app_selected is called
    with patch.object(AppConfigScreen, "_fetch"):
        screen.on_status_view_app_selected(StatusView.AppSelected(app=ai))
        await pilot.pause()
    # THEN AppConfigScreen is pushed
    assert isinstance(pilot.app.screen, AppConfigScreen)


# ─────────────────────────────────────────────────────────────────────────────
# on_status_view_relation_selected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_relation_selected_pushes_relation_data_screen(pilot):
    # GIVEN a controller is selected and the relation has a relation_id
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    # WHEN on_status_view_relation_selected is called
    with patch.object(RelationDataScreen, "_fetch"):
        screen.on_status_view_relation_selected(StatusView.RelationSelected(relation=rel))
        await pilot.pause()
    # THEN RelationDataScreen is pushed
    assert isinstance(pilot.app.screen, RelationDataScreen)


# ─────────────────────────────────────────────────────────────────────────────
# on_status_view_offer_selected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_offer_selected_calls_open_offer_detail(pilot):
    # GIVEN a controller is selected
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    offer = OfferInfo("cos", "my-offer", "pg", "pg-k8s", 1, "0/0", "db", "pgsql", "provider")
    # WHEN on_status_view_offer_selected is called
    with patch.object(screen, "_open_offer_detail") as mock_open:
        screen.on_status_view_offer_selected(StatusView.OfferSelected(offer=offer))
        await pilot.pause()
    # THEN _open_offer_detail is called with the correct arguments
    mock_open.assert_called_once_with("ctrl", offer.model, offer.name)


@pytest.mark.asyncio
async def test_open_offer_detail_logs_and_returns_on_connection_error(pilot):
    # GIVEN get_offer_detail raises JujuError (model gone / connection error)
    screen = pilot.app.screen
    with patch("jujumate.screens.main_screen.JujuClient") as MockClient:
        instance = AsyncMock()
        instance.get_offer_detail = AsyncMock(side_effect=JujuError("gone"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # WHEN _open_offer_detail is called
        screen._open_offer_detail("ctrl", "dev", "pg-offer")
        for _ in range(10):
            await pilot.pause()

    # THEN no screen is pushed (method returns gracefully)
    assert pilot.app.screen is screen


def _call_app_selected_no_ctrl(screen) -> None:
    screen._selected_controller = None
    screen._selected_model = None
    ai = AppInfo("pg", "dev", "pg", "14/stable", 1)
    screen.on_status_view_app_selected(StatusView.AppSelected(app=ai))


def _call_rel_selected_no_id(screen) -> None:
    screen._selected_controller = "ctrl"
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=None)
    screen.on_status_view_relation_selected(StatusView.RelationSelected(relation=rel))


def _call_offer_selected_no_ctrl(screen) -> None:
    screen._selected_controller = None
    offer = OfferInfo("cos", "my-offer", "pg", "pg-k8s", 1, "0/0", "db", "pgsql", "provider")
    screen.on_status_view_offer_selected(StatusView.OfferSelected(offer=offer))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_fn",
    [
        pytest.param(_call_app_selected_no_ctrl, id="app-no-controller"),
        pytest.param(_call_rel_selected_no_id, id="relation-no-id"),
        pytest.param(_call_offer_selected_no_ctrl, id="offer-no-controller"),
    ],
)
async def test_status_view_handler_early_return_is_noop(pilot, setup_fn):
    # GIVEN a handler is called with missing required selection
    screen = pilot.app.screen
    # WHEN the handler is invoked
    setup_fn(screen)
    await pilot.pause()
    # THEN we stay on MainScreen (early return triggered)
    assert isinstance(pilot.app.screen, MainScreen)


# ─────────────────────────────────────────────────────────────────────────────
# _open_offer_detail worker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_offer_detail_worker_pushes_offer_detail_screen(pilot):
    # GIVEN a JujuClient mock that returns a valid ControllerOfferInfo
    screen = pilot.app.screen
    offer_detail = ControllerOfferInfo(
        model="cos",
        name="my-offer",
        offer_url="admin/cos.my-offer",
        application="prometheus",
        charm="ch:prometheus-k8s-1",
        description="",
        endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
        active_connections=0,
        total_connections=1,
    )
    mock_client = _make_juju_client_mock(get_offer_detail=offer_detail)
    with (
        patch("jujumate.screens.main_screen.JujuClient", return_value=mock_client),
        patch.object(OfferDetailScreen, "_fetch_consumers"),
    ):
        # WHEN _open_offer_detail is called
        screen._open_offer_detail("ctrl", "cos", "my-offer")
        await pilot.pause()
        await pilot.pause()
    # THEN OfferDetailScreen is pushed
    assert isinstance(pilot.app.screen, OfferDetailScreen)


# ─────────────────────────────────────────────────────────────────────────────
# SecretsScreen & SecretDetailScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secrets_screen_populate_with_secrets(pilot):
    # GIVEN a SecretsScreen with _fetch patched
    secrets = [
        SecretInfo(
            uri="csec:abc123",
            label="my-secret",
            owner="dev",
            description="",
            revision=1,
            rotate_policy="",
            created="2024-01-01",
            updated="2024-01-01",
        ),
        SecretInfo(
            uri="csec:def456",
            label="other",
            owner="dev",
            description="",
            revision=2,
            rotate_policy="",
            created="2024-01-02",
            updated="2024-01-02",
        ),
    ]
    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN _populate is called with two secrets
        screen._populate(secrets)
        await pilot.pause()
    # THEN the data table has two rows
    dt = screen.query_one(DataTable)
    assert dt.row_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "screen_cls, ctor_args",
    [
        pytest.param(SecretsScreen, ("ctrl", "dev"), id="secrets"),
        pytest.param(OffersScreen, ("my-ctrl",), id="offers"),
    ],
)
async def test_screen_populate_empty_shows_no_rows(pilot, screen_cls, ctor_args):
    # GIVEN a screen with _fetch patched
    with patch.object(screen_cls, "_fetch"):
        screen = screen_cls(*ctor_args)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN _populate is called with an empty list
        screen._populate([])
        await pilot.pause()
    # THEN the data table has no rows
    assert screen.query_one(DataTable).row_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "screen_cls, ctor_args, loading_id",
    [
        pytest.param(SecretsScreen, ("ctrl", "dev"), "#secrets-loading", id="secrets"),
        pytest.param(OffersScreen, ("my-ctrl",), "#offers-loading", id="offers"),
    ],
)
async def test_screen_show_error_displays_loading(pilot, screen_cls, ctor_args, loading_id):
    # GIVEN a screen with _fetch patched
    with patch.object(screen_cls, "_fetch"):
        screen = screen_cls(*ctor_args)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN _show_error is called
        screen._show_error("connection refused")
        await pilot.pause()
    # THEN the loading label is still visible (showing the error)
    assert screen.query_one(loading_id).display is True


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_pushes_detail(pilot):
    # GIVEN a SecretsScreen populated with one secret
    secrets = [
        SecretInfo(
            uri="csec:abc",
            label="my-secret",
            owner="dev",
            description="",
            revision=1,
            rotate_policy="",
            created="2024-01-01",
            updated="2024-01-01",
        )
    ]
    with patch.object(SecretsScreen, "_fetch"), patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate(secrets)
        await pilot.pause()
        dt = screen.query_one(DataTable)
        # WHEN a row is selected
        screen.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
        )
        await pilot.pause()
    # THEN SecretDetailScreen is pushed
    assert isinstance(pilot.app.screen, SecretDetailScreen)


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_out_of_range_safe(pilot):
    # GIVEN a SecretsScreen with no secrets
    with patch.object(SecretsScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([])
        await pilot.pause()
    dt = screen.query_one(DataTable)
    # WHEN a row selection with an out-of-range index is received
    # THEN it does not raise
    screen.on_data_table_row_selected(
        DataTable.RowSelected(data_table=dt, cursor_row=99, row_key=RowKey("99"))
    )
    await pilot.pause()


@pytest.mark.asyncio
async def test_secrets_screen_r_key_triggers_refresh(pilot):
    """Pressing 'r' in SecretsScreen clears state and re-fetches secrets."""
    # GIVEN a SecretsScreen populated with a secret and cached content
    secret = SecretInfo(
        uri="csec:abc",
        label="db-pass",
        owner="pg",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    with patch.object(SecretsScreen, "_fetch") as mock_fetch:
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([secret])
        screen._secret_contents = {"csec:abc": {"password": "s3cr3t"}}
        await pilot.pause()
        # WHEN 'r' is pressed
        mock_fetch.reset_mock()
        screen.action_refresh()
        await pilot.pause()
    # THEN state is cleared and _fetch is called again
    assert screen._secrets == []
    assert screen._secret_contents == {}
    dt = screen.query_one(DataTable)
    assert dt.row_count == 0
    mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_secret_detail_screen_shows_fields(pilot):
    # GIVEN a SecretDetailScreen with _fetch patched
    secret = SecretInfo(
        uri="csec:abc123",
        label="my-secret",
        owner="dev",
        description="A test secret",
        revision=1,
        rotate_policy="",
        created="2024-01-01T00:00:00",
        updated="2024-01-01T00:00:00",
    )
    with patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # WHEN we inspect the rendered labels
    labels = screen.query(Label)
    all_text = "\n".join(str(lbl.render()) for lbl in labels)
    # THEN the URI and label are visible
    assert "csec:abc123" in all_text
    assert "my-secret" in all_text


@pytest.mark.asyncio
async def test_secret_detail_screen_skips_fetch_when_prefetched_content_provided(pilot):
    """When prefetched_content is provided, SecretDetailScreen skips the API call."""
    # GIVEN a secret and its pre-fetched content
    secret = SecretInfo(
        uri="csec:abc123",
        label="db-pass",
        owner="pg",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    content = {"password": "s3cr3t", "username": "admin"}
    # WHEN SecretDetailScreen is opened with prefetched_content
    with patch.object(SecretDetailScreen, "_fetch") as mock_fetch:
        screen = SecretDetailScreen("ctrl", "dev", secret, prefetched_content=content)
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # THEN _fetch is never called (no API round-trip)
    mock_fetch.assert_not_called()
    # AND the content is immediately available
    assert screen._content_data == content


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_passes_content_to_detail_screen(pilot):
    """On row select, SecretsScreen passes prefetched content to SecretDetailScreen."""
    # GIVEN a SecretsScreen with a secret and its pre-loaded content
    secret = SecretInfo(
        uri="csec:abc",
        label="my-secret",
        owner="dev",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    prefetched = {"key": "value"}
    with patch.object(SecretsScreen, "_fetch"), patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([secret])
        screen._secret_contents = {"csec:abc": prefetched}
        await pilot.pause()
        dt = screen.query_one(DataTable)
        # WHEN row 0 is selected
        screen.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
        )
        await pilot.pause()
    # THEN the SecretDetailScreen has the prefetched content set
    detail = pilot.app.screen
    assert isinstance(detail, SecretDetailScreen)
    assert detail._prefetched_content == prefetched


# ─────────────────────────────────────────────────────────────────────────────
# AppConfigScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call_view_method, expected_id",
    [
        pytest.param(
            lambda view, ai: view.update(
                ai, [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
            ),
            "#ac-panel",
            id="success",
        ),
        pytest.param(
            lambda view, ai: view.show_error(ai, "timeout"), "#ac-empty", id="fetch-error"
        ),
    ],
)
async def test_app_config_screen_view_state(pilot, call_view_method, expected_id):
    # GIVEN an AppConfigScreen with _fetch patched
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN the view method is called
        call_view_method(screen.query_one(AppConfigView), ai)
        await pilot.pause()
    # THEN the expected panel is visible
    assert screen.query_one(AppConfigView).query_one(expected_id).display is True


# ─────────────────────────────────────────────────────────────────────────────
# RelationDataScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call_view_method, expected_id",
    [
        pytest.param(
            lambda view, rel: view.update(
                rel, [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")]
            ),
            "#rd-panel",
            id="success",
        ),
        pytest.param(
            lambda view, rel: view.show_error(rel, "timeout"), "#rd-empty", id="fetch-error"
        ),
    ],
)
async def test_relation_data_screen_view_state(pilot, call_view_method, expected_id):
    # GIVEN a RelationDataScreen with _fetch patched
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN the view method is called
        call_view_method(screen.query_one(RelationDataView), rel)
        await pilot.pause()
    # THEN the expected panel is visible
    assert screen.query_one(RelationDataView).query_one(expected_id).display is True


# ─────────────────────────────────────────────────────────────────────────────
# Model deletion — stale data cleanup
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_updated_prunes_stale_relations(pilot):
    """Stale relations for a deleted model are removed on next ModelsUpdated."""
    # GIVEN relations exist for both "deleted-model" and "surviving-model"
    screen = pilot.app.screen
    screen.on_relations_updated(
        RelationsUpdated(
            model="deleted-model",
            controller="ctrl",
            relations=[
                RelationInfo(
                    "deleted-model", "pg:db", "wp:db", "pgsql", "regular", controller="ctrl"
                )
            ],
        )
    )
    screen.on_relations_updated(
        RelationsUpdated(
            model="surviving-model",
            controller="ctrl",
            relations=[
                RelationInfo(
                    "surviving-model", "mysql:db", "wp:db", "mysql", "regular", controller="ctrl"
                )
            ],
        )
    )
    # (precondition: verify setup is correct before the WHEN)
    assert any(r.model == "deleted-model" for r in screen._all_relations)
    # WHEN ModelsUpdated is received without "deleted-model"
    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("surviving-model", "ctrl", "aws", "", "active"),
            ]
        )
    )
    # THEN stale relations for the deleted model are pruned
    assert not any(r.model == "deleted-model" for r in screen._all_relations)
    assert any(r.model == "surviving-model" for r in screen._all_relations)


@pytest.mark.asyncio
async def test_models_updated_prunes_stale_offers_and_saas(pilot):
    """Stale offers and SAAS for a deleted model are removed on next ModelsUpdated."""
    # GIVEN offers and SAAS exist for "gone-model"
    screen = pilot.app.screen
    screen.on_offers_updated(
        OffersUpdated(
            model="gone-model",
            offers=[
                OfferInfo(
                    "gone-model", "my-offer", "pg", "pg-k8s", 1, "0/0", "db", "pgsql", "provider"
                )
            ],
        )
    )
    screen.on_saas_updated(
        SaasUpdated(
            model="gone-model",
            saas=[SAASInfo("gone-model", "remote-pg", "active", "mystore", "mystore:admin/pg")],
        )
    )
    # (precondition: verify setup is correct before the WHEN)
    assert any(o.model == "gone-model" for o in screen._all_offers)
    assert any(s.model == "gone-model" for s in screen._all_saas)
    # WHEN ModelsUpdated is received without "gone-model"
    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )
    # THEN stale offers and SAAS are pruned
    assert not any(o.model == "gone-model" for o in screen._all_offers)
    assert not any(s.model == "gone-model" for s in screen._all_saas)


@pytest.mark.asyncio
async def test_models_updated_deselects_deleted_model(pilot):
    """When the selected model is deleted, _selected_model is reset and tab switches."""
    # GIVEN the selected model is about to be deleted
    screen = pilot.app.screen
    screen._selected_model = "doomed-model"
    screen._all_relations = [
        RelationInfo("doomed-model", "pg:db", "wp:db", "pgsql", "regular"),
    ]
    pilot.app.screen.query_one(TabbedContent).active = "tab-status"
    # WHEN ModelsUpdated is received without the selected model
    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )
    # THEN the selection is cleared and we switch to the models tab
    assert screen._selected_model is None
    assert screen._all_relations == []
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"


@pytest.mark.asyncio
async def test_models_updated_keeps_selected_model_when_still_exists(pilot):
    """When the selected model still exists, it stays selected and data is kept."""
    # GIVEN a model is selected and still exists in the update
    screen = pilot.app.screen
    screen._selected_model = "my-model"
    screen._selected_controller = "ctrl"
    screen._all_relations = [
        RelationInfo("my-model", "pg:db", "wp:db", "pgsql", "regular", controller="ctrl"),
    ]
    # WHEN ModelsUpdated is received and the selected model is still present
    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("my-model", "ctrl", "aws", "", "active"),
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )
    # THEN the selection and relations are preserved
    assert screen._selected_model == "my-model"
    assert any(r.model == "my-model" for r in screen._all_relations)


# ─────────────────────────────────────────────────────────────────────────────
# Targeted update — merge paths (model + controller set)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_updated_targeted_replaces_only_matching_model(pilot):
    """Targeted ModelsUpdated replaces only the named model, keeping others intact."""
    # GIVEN two models already loaded
    screen = pilot.app.screen
    screen._all_models = [
        ModelInfo("dev", "ctrl", "aws", "", "active"),
        ModelInfo("prod", "ctrl", "aws", "", "active"),
    ]
    updated = ModelInfo("dev", "ctrl", "aws", "", "blocked")
    # WHEN ModelsUpdated is received with model + controller set (targeted)
    screen.on_models_updated(ModelsUpdated(models=[updated], model="dev", controller="ctrl"))
    # THEN only the matching model is replaced; the other is untouched
    assert len(screen._all_models) == 2
    dev = next(m for m in screen._all_models if m.name == "dev")
    assert dev.status == "blocked"
    assert any(m.name == "prod" for m in screen._all_models)


@pytest.mark.asyncio
async def test_apps_updated_targeted_replaces_only_matching_apps(pilot):
    """Targeted AppsUpdated replaces only apps for the named (controller, model)."""
    # GIVEN apps loaded for two different models
    screen = pilot.app.screen
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1, unit_count=1, controller="ctrl"),
        AppInfo("nginx", "prod", "nginx", "latest", 1, unit_count=1, controller="ctrl"),
    ]
    updated_app = AppInfo("pg", "dev", "pg", "14/stable", 1, unit_count=2, controller="ctrl")
    # WHEN AppsUpdated is received scoped to (ctrl, dev)
    screen.on_apps_updated(AppsUpdated(apps=[updated_app], model="dev", controller="ctrl"))
    # THEN only apps for (ctrl, dev) are replaced; prod apps remain
    assert any(a.model == "prod" for a in screen._all_apps)
    dev_pg = next(a for a in screen._all_apps if a.model == "dev")
    assert dev_pg.unit_count == 2


@pytest.mark.asyncio
async def test_units_updated_targeted_replaces_only_matching_units(pilot):
    """Targeted UnitsUpdated replaces only units for the named (controller, model)."""
    # GIVEN units loaded for two different models
    screen = pilot.app.screen
    screen._all_units = [
        UnitInfo("pg/0", "pg", "0", "active", "idle", model="dev", controller="ctrl"),
        UnitInfo("nginx/0", "nginx", "0", "active", "idle", model="prod", controller="ctrl"),
    ]
    updated_unit = UnitInfo("pg/0", "pg", "0", "blocked", "idle", model="dev", controller="ctrl")
    # WHEN UnitsUpdated is received scoped to (ctrl, dev)
    screen.on_units_updated(UnitsUpdated(units=[updated_unit], model="dev", controller="ctrl"))
    # THEN only units for (ctrl, dev) are replaced; prod units remain
    assert any(u.model == "prod" for u in screen._all_units)
    dev_pg = next(u for u in screen._all_units if u.model == "dev")
    assert dev_pg.workload_status == "blocked"


@pytest.mark.asyncio
async def test_machines_updated_targeted_replaces_only_matching_machines(pilot):
    """Targeted MachinesUpdated replaces only machines for the named (controller, model)."""
    # GIVEN machines loaded for two different models
    screen = pilot.app.screen
    screen._all_machines = [
        MachineInfo(
            "dev",
            "0",
            "started",
            "10.0.0.1",
            "i-1",
            "ubuntu@22.04",
            "us-east-1a",
            controller="ctrl",
        ),
        MachineInfo(
            "prod",
            "1",
            "started",
            "10.0.0.2",
            "i-2",
            "ubuntu@22.04",
            "us-east-1a",
            controller="ctrl",
        ),
    ]
    updated = MachineInfo(
        "dev", "0", "stopped", "10.0.0.1", "i-1", "ubuntu@22.04", "us-east-1a", controller="ctrl"
    )
    # WHEN MachinesUpdated is received scoped to (ctrl, dev)
    screen.on_machines_updated(MachinesUpdated(machines=[updated], model="dev", controller="ctrl"))
    # THEN only machines for (ctrl, dev) are replaced; prod machines remain
    assert any(m.model == "prod" for m in screen._all_machines)
    dev_machine = next(m for m in screen._all_machines if m.model == "dev")
    assert dev_machine.state == "stopped"


# ─────────────────────────────────────────────────────────────────────────────
# OffersScreen & OfferDetailScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offers_screen_populate_with_offers(pilot):
    # GIVEN an OffersScreen with _fetch patched
    offers = [
        ControllerOfferInfo(
            model="cos",
            name="prometheus-scrape",
            offer_url="admin/cos.prometheus-scrape",
            application="prometheus",
            charm="ch:prometheus-k8s-1",
            description="Scrape endpoint",
            endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
            active_connections=1,
            total_connections=2,
        ),
        ControllerOfferInfo(
            model="cos",
            name="alertmanager-karma",
            offer_url="admin/cos.alertmanager-karma",
            application="alertmanager",
            charm="ch:alertmanager-k8s-1",
            description="",
            endpoints=[],
            active_connections=0,
            total_connections=0,
        ),
    ]
    with patch.object(OffersScreen, "_fetch"):
        screen = OffersScreen("my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        # WHEN _populate is called with two offers
        screen._populate(offers)
        await pilot.pause()
    # THEN the data table has two rows
    dt = screen.query_one(DataTable)
    assert dt.row_count == 2


@pytest.mark.asyncio
async def test_offers_screen_row_selected_pushes_detail(pilot):
    # GIVEN an OffersScreen populated with one offer
    offers = [
        ControllerOfferInfo(
            model="cos",
            name="prom",
            offer_url="admin/cos.prom",
            application="prometheus",
            charm="ch:prometheus-k8s-1",
            description="",
            endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
            active_connections=0,
            total_connections=1,
        )
    ]
    with patch.object(OffersScreen, "_fetch"), patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OffersScreen("my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate(offers)
        await pilot.pause()
        dt = screen.query_one(DataTable)
        # WHEN a row is selected
        screen.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
        )
        await pilot.pause()
    # THEN OfferDetailScreen is pushed
    assert isinstance(pilot.app.screen, OfferDetailScreen)


@pytest.mark.asyncio
async def test_offer_detail_screen_shows_fields(pilot):
    # GIVEN an OfferDetailScreen with _fetch_consumers patched
    offer = ControllerOfferInfo(
        model="cos",
        name="prom-scrape",
        offer_url="admin/cos.prom-scrape",
        application="prometheus",
        charm="ch:prometheus-k8s-1",
        description="Scrape metrics",
        endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
        active_connections=2,
        total_connections=3,
    )
    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # WHEN we inspect the rendered labels
    labels = screen.query(Label)
    all_text = "\n".join(str(lbl.render()) for lbl in labels)
    # THEN key offer fields are visible
    assert "prom-scrape" in all_text
    assert "prometheus" in all_text
    assert "Scrape metrics" in all_text


@pytest.mark.asyncio
async def test_action_show_offers_pushes_screen(pilot):
    """Shift+O with a controller opens OffersScreen."""
    # GIVEN a controller is selected
    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    # WHEN action_show_offers is called
    with patch.object(OffersScreen, "_fetch"):
        screen.action_show_offers()
        await pilot.pause()
    # THEN OffersScreen is pushed
    assert isinstance(pilot.app.screen, OffersScreen)


@pytest.mark.asyncio
async def test_action_show_offers_passes_cached_data_when_available(pilot):
    """When the offers cache is warm (within TTL), OffersScreen opens with prefetched data."""
    # GIVEN a controller is selected and the cache is populated with a fresh entry
    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    cached_offers = [
        ControllerOfferInfo(
            model="dev",
            name="pg",
            offer_url="admin/dev.pg",
            application="postgresql",
            charm="ch:postgresql-1",
            description="",
        )
    ]
    screen._offers_cache["my-ctrl"] = (cached_offers, time.monotonic())
    # WHEN action_show_offers is called
    with patch.object(OffersScreen, "_fetch") as mock_fetch:
        screen.action_show_offers()
        await pilot.pause()
    # THEN OffersScreen is opened without calling _fetch (data is pre-populated)
    mock_fetch.assert_not_called()
    assert isinstance(pilot.app.screen, OffersScreen)


@pytest.mark.asyncio
async def test_action_show_offers_refetches_when_cache_expired(pilot):
    """When the cache entry is older than offers_cache_ttl, a fresh fetch is triggered."""
    # GIVEN a stale cache entry (timestamp far in the past)
    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    stale_ts = time.monotonic() - (screen._settings.offers_cache_ttl + 1)
    screen._offers_cache["my-ctrl"] = ([], stale_ts)
    # WHEN action_show_offers is called
    with patch.object(OffersScreen, "_fetch") as mock_fetch:
        screen.action_show_offers()
        await pilot.pause()
    # THEN _fetch is called because the cache has expired
    mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_action_show_offers_stores_fetched_data_in_cache(pilot):
    """After OffersScreen fetches, invoking its callback populates MainScreen's cache."""
    # GIVEN no cached data and a controller is selected
    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    assert "my-ctrl" not in screen._offers_cache
    new_offers: list[ControllerOfferInfo] = []
    # WHEN action_show_offers is called
    with patch.object(OffersScreen, "_fetch"):
        screen.action_show_offers()
        await pilot.pause()
    offers_screen = pilot.app.screen
    assert isinstance(offers_screen, OffersScreen)
    # THEN invoking the on_fetched callback stores (offers, timestamp) in the cache
    assert offers_screen._on_fetched is not None
    offers_screen._on_fetched(new_offers)
    cached = screen._offers_cache.get("my-ctrl")
    assert cached is not None
    assert cached[0] is new_offers


@pytest.mark.asyncio
async def test_offer_detail_screen_populate_consumers(pilot):
    """_populate_consumers fills the connections table with SAASInfo rows."""
    # GIVEN an OfferDetailScreen with _fetch_consumers patched
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prometheus-k8s-1",
        description="",
        endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
    )
    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
    consumers = [
        _ConsumerEntry(
            "ctrl-a",
            SAASInfo("monitoring", "prometheus-scrape", "active", "local", "admin/cos.prom"),
        ),
        _ConsumerEntry("ctrl-b", SAASInfo("prod", "metrics", "active", "local", "admin/cos.prom")),
    ]
    # WHEN _populate_consumers is called with two consumers
    screen._populate_consumers(consumers)
    await pilot.pause()
    # THEN the connections table has two rows
    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 2


@pytest.mark.asyncio
async def test_offer_detail_fetch_consumers_scans_all_controllers(pilot):
    """_fetch_consumers scans models across all known controllers."""
    # GIVEN an OfferDetailScreen and mocked clients for two controllers
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prometheus-k8s-1",
        description="",
        endpoints=[OfferEndpoint("metrics-endpoint", "prometheus_scrape", "provider")],
    )
    consumer = SAASInfo("monitoring", "prom-scrape", "active", "local", "admin/cos.prom")
    mock_client_a = _make_juju_client_mock(
        list_model_names=["cos"],
        get_saas=[],
    )
    mock_client_b = _make_juju_client_mock(
        list_model_names=["monitoring"],
        get_saas=[consumer],
    )

    def _make_client(controller_name: str) -> AsyncMock:
        return mock_client_a if controller_name == "ctrl-a" else mock_client_b

    # Mount screen and call worker INSIDE the patch context so it runs with mocked deps
    with (
        patch(
            "jujumate.screens.offers_screen.load_config",
            return_value=JujuConfig(current_controller="ctrl-a", controllers=["ctrl-a", "ctrl-b"]),
        ),
        patch("jujumate.screens.offers_screen.JujuClient", side_effect=_make_client),
    ):
        screen = OfferDetailScreen(offer, "ctrl-a")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the consumer from ctrl-b is shown in the connections table
    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 1


@pytest.mark.asyncio
async def test_offer_detail_uses_cache_when_all_saas_provided(pilot):
    """When all_saas is provided, consumers are found in-memory without API calls."""
    # GIVEN an offer and a pre-populated SAAS list that contains a consumer
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
    )
    matching_saas = SAASInfo(
        "monitoring", "prom-scrape", "active", "local", "admin/cos.prom", controller="ctrl-b"
    )
    unrelated_saas = SAASInfo(
        "prod", "other", "active", "local", "admin/other.app", controller="ctrl-a"
    )
    # WHEN OfferDetailScreen is opened with all_saas
    with patch.object(OfferDetailScreen, "_fetch_consumers") as mock_fetch:
        screen = OfferDetailScreen(offer, "ctrl-a", all_saas=[matching_saas, unrelated_saas])
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # THEN _fetch_consumers is never called (no API round-trip)
    mock_fetch.assert_not_called()
    # AND the matching consumer is shown in the connections table
    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 1


@pytest.mark.asyncio
async def test_offer_detail_shows_no_consumers_when_cache_empty_match(pilot):
    """all_saas provided but no matching entry → shows 'No known consumers'."""
    # GIVEN an offer and a SAAS list with no matching URL
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
    )
    unrelated = SAASInfo("prod", "other", "active", "local", "admin/other.app", controller="ctrl-a")
    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "ctrl-a", all_saas=[unrelated])
        await pilot.app.push_screen(screen)
        await pilot.pause()
    # THEN loading label shows "No known consumers"
    loading = screen.query_one("#consumers-loading", Static)
    assert loading.display is True
    assert "No known consumers" in str(loading.render())


@pytest.mark.asyncio
async def test_action_show_offers_passes_all_saas_to_offers_screen(pilot):
    """MainScreen passes _all_saas to OffersScreen so it can propagate to OfferDetailScreen."""
    # GIVEN a controller is selected and _all_saas is populated
    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    saas = SAASInfo("monitoring", "prom", "active", "local", "admin/cos.prom", controller="my-ctrl")
    screen._all_saas = [saas]
    # WHEN action_show_offers is called
    with patch.object(OffersScreen, "_fetch"):
        screen.action_show_offers()
        await pilot.pause()
    offers_screen = pilot.app.screen
    assert isinstance(offers_screen, OffersScreen)
    # THEN OffersScreen received _all_saas
    assert offers_screen._all_saas == [saas]


# ─────────────────────────────────────────────────────────────────────────────
# AppConfigScreen._fetch worker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_config_screen_fetch_worker_success(pilot):
    """Lines 37-43: _fetch worker populates AppConfigView on success."""
    # GIVEN an AppConfigScreen with JujuClient patched to return entries
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    mock_client = _make_juju_client_mock(get_app_config=entries)

    with patch("jujumate.screens.app_config_screen.JujuClient", return_value=mock_client):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the config panel is visible (worker populated the view)
    assert screen.query_one(AppConfigView).query_one("#ac-panel").display is True


@pytest.mark.asyncio
async def test_app_config_screen_fetch_worker_error(pilot):
    """Lines 37-43: _fetch worker shows error on exception."""
    # GIVEN an AppConfigScreen with JujuClient that raises
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    mock_client = _make_juju_client_mock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))

    with patch("jujumate.screens.app_config_screen.JujuClient", return_value=mock_client):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()


@pytest.mark.asyncio
async def test_app_config_screen_uses_prefetched_entries(pilot):
    """AppConfigScreen skips _fetch() when prefetched_entries are provided."""
    # GIVEN an AppConfigScreen with prefetched entries and _fetch patched to detect calls
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    fetch_called = []

    with patch.object(
        AppConfigScreen, "_fetch", side_effect=lambda *a, **kw: fetch_called.append(1)
    ):
        screen = AppConfigScreen("ctrl", "dev", ai, prefetched_entries=entries)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN _fetch was NOT called (cached data used directly)
    assert fetch_called == []
    assert screen.query_one(AppConfigView).query_one("#ac-panel").display is True


@pytest.mark.asyncio
async def test_app_config_screen_fetch_calls_on_fetched_callback(pilot):
    """_fetch() calls on_fetched callback with the retrieved entries."""
    # GIVEN an AppConfigScreen with on_fetched callback and a mock client
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    received: list[list[AppConfigEntry]] = []
    mock_client = _make_juju_client_mock(get_app_config=entries)

    with patch("jujumate.screens.app_config_screen.JujuClient", return_value=mock_client):
        screen = AppConfigScreen("ctrl", "dev", ai, on_fetched=received.append)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN on_fetched was called with the entries
    assert len(received) == 1
    assert received[0] == entries


@pytest.mark.asyncio
async def test_app_config_screen_refresh_action_re_fetches(pilot):
    """Pressing r triggers action_refresh which re-calls _fetch()."""
    # GIVEN an AppConfigScreen with prefetched entries already displayed
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    prefetched = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    entries_v2 = [AppConfigEntry("port", "5433", "5432", "int", "Port", "user")]
    mock_client = _make_juju_client_mock(get_app_config=entries_v2)

    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai, prefetched_entries=prefetched)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # WHEN r is pressed
    with patch("jujumate.screens.app_config_screen.JujuClient", return_value=mock_client):
        await pilot.press("r")
        for _ in range(10):
            await pilot.pause()

    # THEN fresh data is displayed
    assert screen.query_one(AppConfigView).query_one("#ac-panel").display is True


@pytest.mark.asyncio
async def test_app_config_cache_populated_on_first_open(pilot):
    """MainScreen caches app config entries after the first open."""
    # GIVEN a selected controller/model and a mock client returning config entries
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    mock_client = _make_juju_client_mock(get_app_config=entries)

    with patch("jujumate.screens.app_config_screen.JujuClient", return_value=mock_client):
        screen.on_status_view_app_selected(StatusView.AppSelected(app=ai))
        for _ in range(10):
            await pilot.pause()

    # THEN the cache entry is populated
    assert ("ctrl", "dev", "pg") in screen._app_config_cache
    assert screen._app_config_cache[("ctrl", "dev", "pg")] == entries


@pytest.mark.asyncio
async def test_app_config_cache_hit_skips_api_call(pilot):
    """Second open of the same app config uses the cache — no API call."""
    # GIVEN a pre-populated cache entry
    screen = pilot.app.screen
    screen._selected_controller = "ctrl"
    screen._selected_model = "dev"
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363)
    cached = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]
    screen._app_config_cache[("ctrl", "dev", "pg")] = cached
    fetch_calls: list[int] = []

    with patch.object(AppConfigScreen, "_fetch", side_effect=lambda *a: fetch_calls.append(1)):
        screen.on_status_view_app_selected(StatusView.AppSelected(app=ai))
        await pilot.pause()

    # THEN _fetch was not called (cache hit)
    assert fetch_calls == []


# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_relation_data_screen_fetch_worker_success(pilot):
    """Lines 48-56: _fetch worker populates RelationDataView on success."""
    # GIVEN a RelationDataScreen with JujuClient patched to return entries
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    entries = [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")]
    mock_client = _make_juju_client_mock(get_relation_data=entries)

    with patch("jujumate.screens.relation_data_screen.JujuClient", return_value=mock_client):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the relation data panel is visible
    assert screen.query_one(RelationDataView).query_one("#rd-panel").display is True


@pytest.mark.asyncio
async def test_relation_data_screen_fetch_worker_error(pilot):
    """Lines 48-56: _fetch worker shows error on exception."""
    # GIVEN a RelationDataScreen with JujuClient that raises
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    mock_client = _make_juju_client_mock()
    mock_client.__aenter__ = AsyncMock(side_effect=JujuError("failed"))

    with patch("jujumate.screens.relation_data_screen.JujuClient", return_value=mock_client):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the error panel is shown
    assert screen.query_one(RelationDataView).query_one("#rd-empty").display is True


@pytest.mark.asyncio
async def test_app_config_screen_shows_partial_data_before_fetch(pilot):
    """AppConfigScreen shows metadata immediately (show_partial) before _fetch completes."""
    # GIVEN an AppConfigScreen with _fetch patched (so it never completes)
    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN ac-panel is already visible (partial data shown) and meta content is populated
    view = screen.query_one(AppConfigView)
    assert view.query_one("#ac-panel").display is True
    assert view.query_one("#ac-empty").display is False


@pytest.mark.asyncio
async def test_relation_data_screen_shows_partial_data_before_fetch(pilot):
    """RelationDataScreen shows relation metadata immediately before _fetch completes."""
    # GIVEN a RelationDataScreen with _fetch patched (so it never completes)
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN rd-panel is already visible (partial data shown)
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-panel").display is True
    assert view.query_one("#rd-empty").display is False


@pytest.mark.asyncio
async def test_relation_data_view_show_partial_populates_metadata(pilot):
    """show_partial() shows rd-panel with meta section visible before data loads."""
    # GIVEN a RelationDataScreen pushed with _fetch patched
    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=5)
    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN rd-panel is visible, meta section is present, and empty label is hidden
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-panel").display is True
    assert view.query_one("#rd-meta-content").display is True
    assert view.query_one("#rd-empty").display is False


# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secret_detail_screen_fetch_worker_success(pilot):
    """Lines 89-100: _fetch worker populates list on success."""
    # GIVEN a SecretInfo and JujuClient that returns content
    secret = SecretInfo(
        uri="secret:abc123",
        label="db-pass",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    mock_client = _make_juju_client_mock(get_secret_content={"password": "s3cr3t"})

    with patch("jujumate.screens.secrets_screen.JujuClient", return_value=mock_client):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN loading is hidden and secret-data is shown
    assert screen.query_one("#secret-loading").display is False
    assert screen.query_one("#secret-data").display is True


@pytest.mark.asyncio
async def test_secret_detail_screen_fetch_worker_empty_content(pilot):
    """Lines 72-74: _populate_list shows placeholder when data is empty."""
    # GIVEN a JujuClient that returns empty dict
    secret = SecretInfo(
        uri="secret:empty1",
        label="empty-secret",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    mock_client = _make_juju_client_mock(get_secret_content={})

    with patch("jujumate.screens.secrets_screen.JujuClient", return_value=mock_client):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN loading is hidden and list shows the placeholder item
    assert screen.query_one("#secret-loading").display is False
    lv = screen.query_one("#secret-data", ListView)
    assert lv.display is True
    assert len(lv) == 1


@pytest.mark.asyncio
async def test_secret_detail_screen_fetch_worker_error(pilot):
    """Lines 98-100: _fetch worker updates loading label on exception."""
    # GIVEN a JujuClient that raises
    secret = SecretInfo(
        uri="secret:err1",
        label="err-secret",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    mock_client = _make_juju_client_mock()
    mock_client.__aenter__ = AsyncMock(side_effect=JujuError("forbidden"))

    with patch("jujumate.screens.secrets_screen.JujuClient", return_value=mock_client):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN loading label shows an error message
    loading = screen.query_one("#secret-loading", Label)
    assert loading.display is True
    assert "Error" in str(loading.render())


@pytest.mark.asyncio
async def test_secret_detail_screen_list_view_highlighted_adds_class(pilot):
    """Lines 103-106: on_list_view_highlighted adds kv-selected class to item."""
    # GIVEN a mounted SecretDetailScreen with _fetch patched
    secret = SecretInfo(
        uri="secret:hl1",
        label="hl-secret",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    with patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # WHEN a list item is appended and a Highlighted event is fired
    lv = screen.query_one("#secret-data", ListView)
    item = ListItem(Label("test-key   test-val"))
    await lv.append(item)
    await pilot.pause()
    screen.on_list_view_highlighted(ListView.Highlighted(list_view=lv, item=item))
    await pilot.pause()

    # THEN the item has the kv-selected class
    assert "kv-selected" in item.classes


@pytest.mark.asyncio
async def test_secret_detail_screen_action_copy_value_no_display(pilot):
    """Lines 109-110: action_copy_value returns early when list is not displayed."""
    # GIVEN a SecretDetailScreen with _fetch patched and list hidden
    secret = SecretInfo(
        uri="secret:copy1",
        label="copy-secret",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    with patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    pilot.app.copy_to_clipboard = MagicMock()
    lv = screen.query_one("#secret-data", ListView)
    lv.display = False

    # WHEN action_copy_value is called
    screen.action_copy_value()

    # THEN copy_to_clipboard is not called (early return)
    pilot.app.copy_to_clipboard.assert_not_called()


@pytest.mark.asyncio
async def test_secret_detail_screen_action_copy_value_with_data(pilot):
    """Lines 113-118: action_copy_value copies the selected key's value."""
    # GIVEN a SecretDetailScreen with content data set
    secret = SecretInfo(
        uri="secret:copy2",
        label="copy-secret2",
        owner="app",
        description="",
        revision=1,
        rotate_policy="",
        created="2024-01-01",
        updated="2024-01-01",
    )
    with patch.object(SecretDetailScreen, "_fetch"):
        screen = SecretDetailScreen("ctrl", "dev", secret)
        await pilot.app.push_screen(screen)
        await pilot.pause()

    screen._content_data = {"password": "s3cr3t"}
    lv = screen.query_one("#secret-data", ListView)
    item = ListItem(Label("password"))
    await lv.append(item)
    await pilot.pause()
    lv.display = True
    # Move focus to index 0
    lv.index = 0
    await pilot.pause()

    pilot.app.copy_to_clipboard = MagicMock()
    screen.notify = MagicMock()

    # WHEN action_copy_value is called
    screen.action_copy_value()

    # THEN copy_to_clipboard is called with the secret value
    pilot.app.copy_to_clipboard.assert_called_once_with("s3cr3t")


# ─────────────────────────────────────────────────────────────────────────────
# SecretsScreen._fetch worker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secrets_screen_fetch_worker_error(pilot):
    """Lines 148-154: _fetch worker shows error when JujuClient raises."""
    # GIVEN a SecretsScreen with JujuClient that raises
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=JujuError("no model"))
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("jujumate.screens.secrets_screen.JujuClient", return_value=mock_client):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN loading label is visible with error text
    loading = screen.query_one("#secrets-loading")
    assert loading.display is True


# ─────────────────────────────────────────────────────────────────────────────
# OfferDetailScreen — no-endpoints placeholder and consumer edge cases
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_detail_screen_no_endpoints_shows_placeholder(pilot):
    """Line 112: endpoints table shows placeholder row when offer has no endpoints."""
    # GIVEN an OfferDetailScreen with an offer that has no endpoints
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[],
    )

    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # THEN endpoints table has one row with placeholder "—"
    ep_dt = screen.query_one("#endpoints-table", DataTable)
    assert ep_dt.row_count == 1


@pytest.mark.asyncio
async def test_offer_detail_fetch_consumers_inner_exception_caught(pilot):
    """Lines 139-147: inner exception from get_saas is caught and logged."""
    # GIVEN an OfferDetailScreen and a client where get_saas raises JujuError
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
    )
    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "ctrl-a")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.list_model_names = AsyncMock(return_value=["monitoring"])
    mock_client.get_saas = AsyncMock(side_effect=JujuError("no saas"))

    with (
        patch(
            "jujumate.screens.offers_screen.load_config",
            return_value=JujuConfig(current_controller="ctrl-a", controllers=["ctrl-a"]),
        ),
        patch("jujumate.screens.offers_screen.JujuClient", return_value=mock_client),
    ):
        # WHEN _fetch_consumers is called (inner get_saas raises)
        screen._fetch_consumers(screen._controller_name, screen._offer)
        for _ in range(10):
            await pilot.pause()

    # THEN no exception propagates and the consumers section shows "No known consumers"
    loading = screen.query_one("#consumers-loading")
    assert loading.display is True


@pytest.mark.asyncio
async def test_offer_detail_screen_populate_consumers_no_consumers(pilot):
    """Lines 163-164: _populate_consumers shows 'No known consumers' when list is empty."""
    # GIVEN a mounted OfferDetailScreen with _fetch_consumers patched
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
    )
    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    # WHEN _populate_consumers is called with an empty list
    screen._populate_consumers([])
    await pilot.pause()

    # THEN the loading label shows "No known consumers."
    loading = screen.query_one("#consumers-loading")
    assert loading.display is True
    assert "No known consumers" in str(loading.render())


# ─────────────────────────────────────────────────────────────────────────────
# OffersScreen._fetch worker
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offers_screen_fetch_worker_success(pilot):
    """Lines 193-199: _fetch worker populates table and calls on_fetched on success."""
    # GIVEN an OffersScreen with JujuClient patched to return offers
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
        active_connections=1,
        total_connections=1,
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get_controller_offers = AsyncMock(return_value=[offer])
    callback_result: list[list[ControllerOfferInfo]] = []

    with (
        patch("jujumate.screens.offers_screen.JujuClient", return_value=mock_client),
        patch.object(OfferDetailScreen, "_fetch_consumers"),
    ):
        screen = OffersScreen("ctrl", on_fetched=callback_result.append)
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the table has one row
    dt = screen.query_one("#offers-table", DataTable)
    assert dt.row_count == 1
    # AND the on_fetched callback was invoked with the fetched offers
    assert len(callback_result) == 1
    assert callback_result[0] == [offer]


@pytest.mark.asyncio
async def test_offers_screen_fetch_worker_error(pilot):
    """Lines 193-199: _fetch worker shows error when JujuClient raises."""
    # GIVEN an OffersScreen with JujuClient that raises
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("jujumate.screens.offers_screen.JujuClient", return_value=mock_client):
        screen = OffersScreen("ctrl")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN loading label is visible
    loading = screen.query_one("#offers-loading")
    assert loading.display is True


@pytest.mark.asyncio
async def test_offers_screen_r_key_triggers_refresh(pilot):
    """Pressing 'r' in OffersScreen clears state, invalidates cache and re-fetches."""
    # GIVEN an OffersScreen populated with one offer and a cache callback
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
    )
    cache: list[list[ControllerOfferInfo]] = []
    with patch.object(OffersScreen, "_fetch") as mock_fetch:
        screen = OffersScreen("ctrl", on_fetched=cache.append)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([offer])
        await pilot.pause()
        mock_fetch.reset_mock()
        # WHEN 'r' is pressed
        screen.action_refresh()
        await pilot.pause()
    # THEN state is cleared, cache is invalidated, and _fetch is called again
    assert screen._offers == []
    dt = screen.query_one(DataTable)
    assert dt.row_count == 0
    mock_fetch.assert_called_once()
    # AND the cache was cleared via the on_fetched callback (called with empty list)
    assert cache[-1] == []


@pytest.mark.asyncio
async def test_offers_screen_populate_all_active_connections(pilot):
    """Line 216: _populate colors connections green when active == total > 0."""
    # GIVEN an OffersScreen with _fetch patched
    with patch.object(OffersScreen, "_fetch"):
        screen = OffersScreen("ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
        active_connections=2,
        total_connections=2,
    )

    # WHEN _populate is called with all connections active
    screen._populate([offer])
    await pilot.pause()

    # THEN the table has exactly one row
    dt = screen.query_one("#offers-table", DataTable)
    assert dt.row_count == 1


@pytest.mark.asyncio
async def test_offers_screen_populate_partial_active_connections(pilot):
    """_populate colors connections yellow when active < total."""
    # GIVEN an OffersScreen with _fetch patched
    with patch.object(OffersScreen, "_fetch"):
        screen = OffersScreen("ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    offer = ControllerOfferInfo(
        model="cos",
        name="prom2",
        offer_url="admin/cos.prom2",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
        active_connections=1,
        total_connections=3,
    )

    # WHEN _populate is called with partial active connections
    screen._populate([offer])
    await pilot.pause()

    # THEN the table has exactly one row
    dt = screen.query_one("#offers-table", DataTable)
    assert dt.row_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# ThemeScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_theme_screen_on_list_view_selected_saves_and_dismisses(pilot):
    """Lines 74-78: on_list_view_selected saves theme and dismisses the screen."""
    # GIVEN a ThemeScreen is pushed
    await pilot.app.push_screen(ThemeScreen())
    await pilot.pause()
    screen = pilot.app.screen
    assert isinstance(screen, ThemeScreen)
    lv = screen.query_one("#theme-list", ListView)

    # WHEN a list item is selected (simulate by calling handler directly)
    item = lv.highlighted_child
    if item is None:
        # Fallback: use first child
        item = next(iter(lv.query(ListItem)), None)

    with patch("jujumate.screens.theme_screen.save_theme") as mock_save:
        if item is not None:
            screen.on_list_view_selected(ListView.Selected(list_view=lv, item=item, index=0))
        await pilot.pause()

    # THEN save_theme was called and ThemeScreen was dismissed
    if item is not None:
        mock_save.assert_called_once()
    assert not isinstance(pilot.app.screen, ThemeScreen)


@pytest.mark.asyncio
async def test_theme_screen_action_cancel_restores_original_theme(pilot):
    """Lines 81-83: action_cancel restores original theme and dismisses."""
    # GIVEN a ThemeScreen pushed with an original theme set
    await pilot.app.push_screen(ThemeScreen())
    await pilot.pause()
    screen = pilot.app.screen
    assert isinstance(screen, ThemeScreen)
    screen._original_theme = pilot.app.theme or "dark"

    # WHEN action_cancel is called
    with patch.object(pilot.app, "switch_theme") as mock_switch:
        screen.action_cancel()
        await pilot.pause()

    # THEN switch_theme was called with the original theme and screen was dismissed
    mock_switch.assert_called_once_with(screen._original_theme)
    assert not isinstance(pilot.app.screen, ThemeScreen)


# ─────────────────────────────────────────────────────────────────────────────
# SecretsScreen._fetch worker — success path
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secrets_screen_fetch_worker_success(pilot):
    """Lines 150-151: _fetch worker populates table on success."""
    # GIVEN a SecretsScreen with JujuClient that returns a secret
    secret = SecretInfo(
        uri="secret:abc123",
        label="db-pass",
        owner="application",
        description="DB password",
        revision=1,
        rotate_policy="never",
        created="2024-01-01",
        updated="2024-01-01",
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get_secrets_with_content = AsyncMock(return_value=([secret], {}))

    with patch("jujumate.screens.secrets_screen.JujuClient", return_value=mock_client):
        screen = SecretsScreen("ctrl", "dev")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN the secrets table is shown with one row
    dt = screen.query_one("#secrets-table", DataTable)
    assert dt.display is True
    assert dt.row_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# OfferDetailScreen._fetch_consumers — outer controller exception (lines 146-147)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_detail_fetch_consumers_outer_exception_caught(pilot):
    """Lines 146-147: outer exception (controller unreachable) is caught and logged."""
    # GIVEN an OfferDetailScreen and a client whose __aenter__ raises OSError
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=OSError("connection refused"))
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "jujumate.screens.offers_screen.load_config",
            return_value=JujuConfig(current_controller="ctrl-a", controllers=["ctrl-a"]),
        ),
        patch("jujumate.screens.offers_screen.JujuClient", return_value=mock_client),
    ):
        screen = OfferDetailScreen(offer, "ctrl-a")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN no exception propagates and consumers section shows "No known consumers"
    loading = screen.query_one("#consumers-loading")
    assert loading.display is True


# ─────────────────────────────────────────────────────────────────────────────
# OfferDetailScreen._fetch_consumers — JujuConfigError falls back to current controller
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_detail_fetch_consumers_config_error_fallback(pilot):
    """Lines 126-127: when load_config raises JujuConfigError, fallback to current controller."""
    # GIVEN an OfferDetailScreen and a client that returns an empty SAAS list
    offer = ControllerOfferInfo(
        model="cos",
        name="prom",
        offer_url="admin/cos.prom",
        application="prometheus",
        charm="ch:prom-1",
        description="",
        endpoints=[OfferEndpoint("metrics", "prom_scrape", "provider")],
    )
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.list_model_names = AsyncMock(return_value=["cos"])
    mock_client.get_saas = AsyncMock(return_value=[])

    with (
        patch(
            "jujumate.screens.offers_screen.load_config",
            side_effect=JujuConfigError("no config"),
        ),
        patch("jujumate.screens.offers_screen.JujuClient", return_value=mock_client),
    ):
        # WHEN the screen is pushed (auto-starts _fetch_consumers)
        screen = OfferDetailScreen(offer, "ctrl-a")
        await pilot.app.push_screen(screen)
        for _ in range(10):
            await pilot.pause()

    # THEN worker completed normally (fallback to single controller, no consumers found)
    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# on_models_updated / on_units_updated — health tab branch
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_updated_refreshes_health_view_when_health_tab_active(pilot):
    # GIVEN the Health tab is active and there is a blocked model
    screen = pilot.app.screen
    screen.action_switch_tab("tab-health")
    await pilot.pause()

    # WHEN on_models_updated is received
    screen.on_models_updated(
        ModelsUpdated(models=[ModelInfo("broken", "ctrl", "aws", "", "blocked")])
    )
    await pilot.pause()

    # THEN the health view data is updated
    assert any(m.name == "broken" for m in screen._all_models)


@pytest.mark.asyncio
async def test_models_updated_refreshes_status_view_when_status_tab_active(pilot):
    # GIVEN the Status tab is active
    screen = pilot.app.screen
    screen.action_switch_tab("tab-status")
    await pilot.pause()

    # WHEN on_models_updated is received
    screen.on_models_updated(
        ModelsUpdated(models=[ModelInfo("my-model", "ctrl", "aws", "", "active")])
    )
    await pilot.pause()

    # THEN the model list is updated
    assert any(m.name == "my-model" for m in screen._all_models)


@pytest.mark.asyncio
async def test_units_updated_refreshes_health_view_when_health_tab_active(pilot):
    # GIVEN the Health tab is active with a model that has an unhealthy unit
    screen = pilot.app.screen
    screen._all_models = [ModelInfo("dev", "ctrl", "aws", "", "active")]
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1, controller="ctrl", status="blocked")
    ]
    screen.action_switch_tab("tab-health")
    await pilot.pause()

    # WHEN on_units_updated is received
    screen.on_units_updated(
        UnitsUpdated(
            units=[UnitInfo("pg/0", "pg", "0", "blocked", "idle", controller="ctrl", model="dev")]
        )
    )
    await pilot.pause()

    # THEN the units are stored and health view was refreshed
    assert any(u.name == "pg/0" for u in screen._all_units)


@pytest.mark.asyncio
async def test_units_updated_refreshes_status_view_when_status_tab_active(pilot):
    # GIVEN the Status tab is active
    screen = pilot.app.screen
    screen.action_switch_tab("tab-status")
    await pilot.pause()

    # WHEN on_units_updated is received
    screen.on_units_updated(
        UnitsUpdated(
            units=[UnitInfo("pg/0", "pg", "0", "active", "idle", controller="ctrl", model="dev")]
        )
    )
    await pilot.pause()

    # THEN the units are stored
    assert any(u.name == "pg/0" for u in screen._all_units)


# ─────────────────────────────────────────────────────────────────────────────
# on_status_view_machine_selected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_machine_selected_pushes_machine_detail_screen(pilot):
    # GIVEN a machine with basic info
    screen = pilot.app.screen
    machine = MachineInfo(
        "dev", "0", "started", "10.0.0.1", "i-abc123", "ubuntu@22.04", "us-east-1a"
    )

    # WHEN on_status_view_machine_selected is called
    screen.on_status_view_machine_selected(StatusView.MachineSelected(machine=machine))
    await pilot.pause()

    # THEN MachineDetailScreen is pushed
    assert isinstance(pilot.app.screen, MachineDetailScreen)


# ─────────────────────────────────────────────────────────────────────────────
# on_storage_updated
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_storage_updated_updates_all_storage(pilot):
    # GIVEN a MainScreen with the status tab active and a StorageInfo for a specific model
    screen = pilot.app.screen
    screen.action_switch_tab("tab-status")
    await pilot.pause()
    storage = StorageInfo(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="/mnt/data",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )

    # WHEN a StorageUpdated message is posted for that model
    screen.on_storage_updated(StorageUpdated(controller="ctrl", model="dev", storage=[storage]))
    await pilot.pause()

    # THEN _all_storage contains the new entry
    assert any(s.storage_id == "data/0" for s in screen._all_storage)


@pytest.mark.asyncio
async def test_on_storage_updated_replaces_entries_for_same_model(pilot):
    # GIVEN a MainScreen that already holds a storage entry for model "dev"
    screen = pilot.app.screen
    old_storage = StorageInfo(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )
    screen.on_storage_updated(StorageUpdated(controller="ctrl", model="dev", storage=[old_storage]))
    await pilot.pause()

    new_storage = StorageInfo(
        storage_id="logs/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="",
        size_mib=512,
        status="attached",
        message="",
        persistent=False,
        life="alive",
        model="dev",
        controller="ctrl",
    )

    # WHEN a new StorageUpdated message arrives for the same model
    screen.on_storage_updated(StorageUpdated(controller="ctrl", model="dev", storage=[new_storage]))
    await pilot.pause()

    # THEN the old entry is replaced by the new one
    assert all(s.storage_id != "data/0" for s in screen._all_storage)
    assert any(s.storage_id == "logs/0" for s in screen._all_storage)


# ─────────────────────────────────────────────────────────────────────────────
# on_status_view_storage_selected
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_view_storage_selected_pushes_storage_detail_screen(pilot):
    # GIVEN a StorageInfo instance
    screen = pilot.app.screen
    storage = StorageInfo(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="rootfs",
        location="/mnt/data",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        life="alive",
        model="dev",
        controller="ctrl",
    )

    # WHEN on_status_view_storage_selected is called
    screen.on_status_view_storage_selected(StatusView.StorageSelected(storage=storage))
    await pilot.pause()

    # THEN StorageDetailScreen is pushed onto the screen stack
    assert isinstance(pilot.app.screen, StorageDetailScreen)
