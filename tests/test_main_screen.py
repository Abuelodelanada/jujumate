from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from juju.errors import JujuError
from textual.widgets import DataTable, Label, TabbedContent
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
    UnitInfo,
)
from jujumate.screens.app_config_screen import AppConfigScreen
from jujumate.screens.main_screen import MainScreen
from jujumate.screens.offers_screen import OfferDetailScreen, OffersScreen, _ConsumerEntry
from jujumate.screens.relation_data_screen import RelationDataScreen
from jujumate.screens.secrets_screen import SecretDetailScreen, SecretsScreen
from jujumate.settings import AppSettings
from jujumate.widgets.app_config_view import AppConfigView
from jujumate.widgets.clouds_view import CloudsView
from jujumate.widgets.controllers_view import ControllersView
from jujumate.widgets.models_view import ModelsView
from jujumate.widgets.navigable_table import NavigableTable
from jujumate.widgets.relation_data_view import RelationDataView
from jujumate.widgets.status_view import StatusView


@pytest.mark.asyncio
async def test_app_mounts_main_screen(pilot):
    assert pilot.app.screen.__class__.__name__ == "MainScreen"


@pytest.mark.asyncio
async def test_default_tab_is_clouds(pilot):
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
    await pilot.press(key)
    assert pilot.app.screen.query_one(TabbedContent).active == expected_tab_id


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
        ControllersUpdated(controllers=[ControllerInfo("ctrl", "aws", "", "3.4.0", model_count=1)])
    )
    screen.on_models_updated(ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")]))
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

    screen = pilot.app.screen
    screen._all_models = [
        ModelInfo("dev", "prod", "aws", "", "available"),
        ModelInfo("staging", "other-ctrl", "aws", "", "available"),
    ]
    screen.on_controllers_view_controller_selected(ControllersView.ControllerSelected(name="prod"))
    await pilot.pause()
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"
    models_view = screen.query_one("#models-view", ModelsView)
    assert len(models_view.query_one(NavigableTable)._rows) == 1


@pytest.mark.asyncio
async def test_model_selected_switches_to_status_and_filters(pilot):

    screen = pilot.app.screen
    screen._all_apps = [
        AppInfo("pg", "dev", "pg", "14/stable", 1, controller="ctrl"),
        AppInfo("mysql", "prod", "mysql", "8/stable", 1, controller="other-ctrl"),
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
async def test_clear_filter_resets_cloud_and_controller(pilot):

    screen = pilot.app.screen
    screen._selected_cloud = "aws"
    screen._selected_controller = "prod"
    screen._selected_model = None  # no model — filter clears normally
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


@pytest.mark.asyncio
async def test_clear_filter_noop_when_model_selected(pilot):
    """Esc does nothing when a model is selected — preserves the full nav state."""
    screen = pilot.app.screen
    screen._selected_cloud = "aws"
    screen._selected_controller = "prod"
    screen._selected_model = "mymodel"
    screen.action_clear_filter()
    await pilot.pause()
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

    loop = MagicMock()
    _asyncio_exception_handler(loop, context)
    if should_suppress:
        loop.default_exception_handler.assert_not_called()
    else:
        loop.default_exception_handler.assert_called_once_with(context)


@pytest.mark.asyncio
async def test_relations_updated_populates_status_view(pilot):

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

    screen = pilot.app.screen
    screen._selected_model = "cos"
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
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-offers-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_machines_updated_populates_status_view(pilot):

    screen = pilot.app.screen
    screen._selected_model = "dev"
    screen._all_models = [ModelInfo("dev", "prod", "aws", "us-east-1", "available")]
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
    status_view = screen.query_one("#status-view", StatusView)
    assert status_view.query_one("#status-machines-table DataTable").row_count == 1


@pytest.mark.asyncio
async def test_fetch_relations_worker_posts_message(pilot):

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
    mock_client.__aenter__ = AsyncMock(side_effect=JujuError("boom"))
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
    screen.on_models_updated(ModelsUpdated(models=[ModelInfo("dev", "ctrl", "aws", "", "active")]))
    screen.on_apps_updated(AppsUpdated(apps=[AppInfo("pg", "dev", "pg", "14/stable", 1)]))
    screen.on_units_updated(UnitsUpdated(units=[UnitInfo("pg/0", "pg", "0", "active", "idle")]))
    with patch.object(screen, "_fetch_relations"):
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
        screen._populate(secrets)
        await pilot.pause()
    dt = screen.query_one(DataTable)
    assert dt.row_count == 2


@pytest.mark.asyncio
async def test_secrets_screen_populate_empty(pilot):

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
        screen.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
        )
        await pilot.pause()
    assert isinstance(pilot.app.screen, SecretDetailScreen)


@pytest.mark.asyncio
async def test_secrets_screen_row_selected_out_of_range_safe(pilot):

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
    labels = screen.query(Label)
    all_text = "\n".join(str(lbl.render()) for lbl in labels)
    assert "csec:abc123" in all_text
    assert "my-secret" in all_text


# ─────────────────────────────────────────────────────────────────────────────
# AppConfigScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_config_screen_success(pilot):

    ai = AppInfo("pg", "dev", "postgresql", "14/stable", 363, status="active")
    entries = [AppConfigEntry("port", "5432", "5432", "int", "Port", "default")]

    with patch.object(AppConfigScreen, "_fetch"):
        screen = AppConfigScreen("ctrl", "dev", ai)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(AppConfigView).update(ai, entries)
        await pilot.pause()
    view = screen.query_one(AppConfigView)
    assert view.query_one("#ac-panel").display is True


@pytest.mark.asyncio
async def test_app_config_screen_fetch_error(pilot):

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

    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)
    entries = [RelationDataEntry("provider", "pg", "host", "10.0.0.1", "app")]

    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(RelationDataView).update(rel, entries)
        await pilot.pause()
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-panel").display is True


@pytest.mark.asyncio
async def test_relation_data_screen_fetch_error(pilot):

    rel = RelationInfo("dev", "pg:db", "wp:db", "pgsql", "regular", relation_id=1)

    with patch.object(RelationDataScreen, "_fetch"):
        screen = RelationDataScreen("ctrl", "dev", rel)
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen.query_one(RelationDataView).show_error(rel, "timeout")
        await pilot.pause()
    view = screen.query_one(RelationDataView)
    assert view.query_one("#rd-empty").display is True


# ─────────────────────────────────────────────────────────────────────────────
# Model deletion — stale data cleanup
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_updated_prunes_stale_relations(pilot):
    """Stale relations for a deleted model are removed on next ModelsUpdated."""
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
    assert any(r.model == "deleted-model" for r in screen._all_relations)

    # ModelsUpdated without "deleted-model" → stale data must be pruned
    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("surviving-model", "ctrl", "aws", "", "active"),
            ]
        )
    )

    assert not any(r.model == "deleted-model" for r in screen._all_relations)
    assert any(r.model == "surviving-model" for r in screen._all_relations)


@pytest.mark.asyncio
async def test_models_updated_prunes_stale_offers_and_saas(pilot):
    """Stale offers and SAAS for a deleted model are removed on next ModelsUpdated."""
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
    assert any(o.model == "gone-model" for o in screen._all_offers)
    assert any(s.model == "gone-model" for s in screen._all_saas)

    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )

    assert not any(o.model == "gone-model" for o in screen._all_offers)
    assert not any(s.model == "gone-model" for s in screen._all_saas)


@pytest.mark.asyncio
async def test_models_updated_deselects_deleted_model(pilot):
    """When the selected model is deleted, _selected_model is reset and tab switches to Models."""
    screen = pilot.app.screen
    screen._selected_model = "doomed-model"
    screen._all_relations = [
        RelationInfo("doomed-model", "pg:db", "wp:db", "pgsql", "regular"),
    ]
    # Start on Status tab to verify we switch away from it.
    pilot.app.screen.query_one(TabbedContent).active = "tab-status"

    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )

    assert screen._selected_model is None
    assert screen._all_relations == []
    assert pilot.app.screen.query_one(TabbedContent).active == "tab-models"


@pytest.mark.asyncio
async def test_models_updated_keeps_selected_model_when_still_exists(pilot):
    """When the selected model still exists, it stays selected and data is kept."""
    screen = pilot.app.screen
    screen._selected_model = "my-model"
    screen._selected_controller = "ctrl"
    screen._all_relations = [
        RelationInfo("my-model", "pg:db", "wp:db", "pgsql", "regular", controller="ctrl"),
    ]

    screen.on_models_updated(
        ModelsUpdated(
            models=[
                ModelInfo("my-model", "ctrl", "aws", "", "active"),
                ModelInfo("other-model", "ctrl", "aws", "", "active"),
            ]
        )
    )

    assert screen._selected_model == "my-model"
    assert any(r.model == "my-model" for r in screen._all_relations)


# ─────────────────────────────────────────────────────────────────────────────
# OffersScreen & OfferDetailScreen
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offers_screen_populate_with_offers(pilot):

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
        screen._populate(offers)
        await pilot.pause()
    dt = screen.query_one(DataTable)
    assert dt.row_count == 2


@pytest.mark.asyncio
async def test_offers_screen_populate_empty(pilot):

    with patch.object(OffersScreen, "_fetch"):
        screen = OffersScreen("my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._populate([])
        await pilot.pause()
    dt = screen.query_one(DataTable)
    assert dt.row_count == 0


@pytest.mark.asyncio
async def test_offers_screen_show_error(pilot):

    with patch.object(OffersScreen, "_fetch"):
        screen = OffersScreen("my-ctrl")
        await pilot.app.push_screen(screen)
        await pilot.pause()
        screen._show_error("connection refused")
        await pilot.pause()
    loading = screen.query_one("#offers-loading")
    assert loading.display is True


@pytest.mark.asyncio
async def test_offers_screen_row_selected_pushes_detail(pilot):

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
        screen.on_data_table_row_selected(
            DataTable.RowSelected(data_table=dt, cursor_row=0, row_key=RowKey("0"))
        )
        await pilot.pause()
    assert isinstance(pilot.app.screen, OfferDetailScreen)


@pytest.mark.asyncio
async def test_offer_detail_screen_shows_fields(pilot):

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
    labels = screen.query(Label)
    all_text = "\n".join(str(lbl.render()) for lbl in labels)
    assert "prom-scrape" in all_text
    assert "prometheus" in all_text
    assert "Scrape metrics" in all_text


@pytest.mark.asyncio
async def test_action_show_offers_no_controller(pilot):
    """Shift+O without a controller notifies the user."""
    screen = pilot.app.screen
    screen._selected_controller = None
    screen.action_show_offers()
    await pilot.pause()


@pytest.mark.asyncio
async def test_action_show_offers_pushes_screen(pilot):
    """Shift+O with a controller opens OffersScreen."""

    screen = pilot.app.screen
    screen._selected_controller = "my-ctrl"
    with patch.object(OffersScreen, "_fetch"):
        screen.action_show_offers()
        await pilot.pause()
    assert isinstance(pilot.app.screen, OffersScreen)


@pytest.mark.asyncio
async def test_offer_detail_screen_populate_consumers(pilot):
    """_populate_consumers fills the connections table with SAASInfo rows."""

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
    screen._populate_consumers(consumers)
    await pilot.pause()

    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 2


@pytest.mark.asyncio
async def test_offer_detail_fetch_consumers_scans_all_controllers(pilot):
    """_fetch_consumers scans models across all known controllers."""

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

    with patch.object(OfferDetailScreen, "_fetch_consumers"):
        screen = OfferDetailScreen(offer, "ctrl-a")
        await pilot.app.push_screen(screen)
        await pilot.pause()

    mock_client_a = AsyncMock()
    mock_client_a.list_model_names = AsyncMock(return_value=["cos"])
    mock_client_a.get_saas = AsyncMock(return_value=[])
    mock_client_a.__aenter__ = AsyncMock(return_value=mock_client_a)
    mock_client_a.__aexit__ = AsyncMock(return_value=False)

    mock_client_b = AsyncMock()
    mock_client_b.list_model_names = AsyncMock(return_value=["monitoring"])
    mock_client_b.get_saas = AsyncMock(return_value=[consumer])
    mock_client_b.__aenter__ = AsyncMock(return_value=mock_client_b)
    mock_client_b.__aexit__ = AsyncMock(return_value=False)

    def _make_client(controller_name: str) -> AsyncMock:
        return mock_client_a if controller_name == "ctrl-a" else mock_client_b

    with (
        patch(
            "jujumate.screens.offers_screen.load_config",
            return_value=JujuConfig(current_controller="ctrl-a", controllers=["ctrl-a", "ctrl-b"]),
        ),
        patch("jujumate.screens.offers_screen.JujuClient", side_effect=_make_client),
    ):
        screen._fetch_consumers(screen._controller_name, screen._offer)
        await pilot.pause()
        await pilot.pause()

    conn_dt = screen.query_one("#connections-table", DataTable)
    assert conn_dt.row_count == 1
