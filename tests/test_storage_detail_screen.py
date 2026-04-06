"""Tests for StorageDetailScreen and its helpers."""

import pytest
from textual.widgets import Static

from jujumate.models.entities import StorageInfo
from jujumate.screens.storage_detail_screen import StorageDetailScreen, _row

# ─────────────────────────────────────────────────────────────────────────────
# _row helper
# ─────────────────────────────────────────────────────────────────────────────


def test_row_pads_label_to_default_width():
    # GIVEN a short label and a value
    # WHEN _row is called
    result = _row("Unit", "mysql/0")
    # THEN the label is padded to 14 chars and value follows
    assert "[bold]Unit          [/bold]mysql/0" in result


def test_row_respects_custom_label_width():
    # GIVEN a custom label width
    # WHEN _row is called with label_width=8
    result = _row("Pool", "ebs", label_width=8)
    # THEN the label is padded to 8 chars
    assert "[bold]Pool    [/bold]ebs" in result


# ─────────────────────────────────────────────────────────────────────────────
# _build_content — field rendering
# ─────────────────────────────────────────────────────────────────────────────


def _make_storage(**kwargs) -> StorageInfo:
    defaults = dict(
        storage_id="data/0",
        unit="mysql/0",
        kind="filesystem",
        pool="kubernetes",
        location="/var/lib/juju/storage/data/0",
        size_mib=1024,
        status="attached",
        message="",
        persistent=True,
        read_only=False,
        life="alive",
        model="cos-lite",
        controller="ck8s",
    )
    defaults.update(kwargs)
    return StorageInfo(**defaults)


def test_build_content_shows_basic_fields():
    # GIVEN a fully populated StorageInfo
    screen = StorageDetailScreen(_make_storage())

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN all key fields appear in the output
    assert "mysql/0" in content
    assert "data/0" in content
    assert "filesystem" in content
    assert "kubernetes" in content
    assert "1 GiB" in content


def test_build_content_shows_message_when_present():
    # GIVEN a storage entry with a non-empty message
    screen = StorageDetailScreen(_make_storage(message="volume detaching"))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the message appears in the output
    assert "volume detaching" in content


def test_build_content_omits_message_when_empty():
    # GIVEN a storage entry with no message
    screen = StorageDetailScreen(_make_storage(message=""))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN no Message row appears
    assert "Message" not in content


def test_build_content_shows_status_placeholder_when_empty():
    # GIVEN a storage entry with no status
    screen = StorageDetailScreen(_make_storage(status=""))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN a dash placeholder is shown for Status
    assert "—" in content


def test_build_content_shows_mountpoint():
    # GIVEN a storage entry with a location
    screen = StorageDetailScreen(_make_storage(location="/mnt/data"))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the mountpoint appears
    assert "/mnt/data" in content


def test_build_content_shows_dash_for_empty_mountpoint():
    # GIVEN a storage entry with no location
    screen = StorageDetailScreen(_make_storage(location=""))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN a dash is shown for Mountpoint
    assert "—" in content


def test_build_content_shows_read_only_yes_when_true():
    # GIVEN a read-only storage entry
    screen = StorageDetailScreen(_make_storage(read_only=True))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'yes' appears for Read Only
    assert "yes" in content


def test_build_content_shows_read_only_no_when_false():
    # GIVEN a writable storage entry
    screen = StorageDetailScreen(_make_storage(read_only=False))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'no' appears for Read Only
    assert "no" in content


def test_build_content_shows_persistent_yes_when_true():
    # GIVEN a persistent storage entry
    screen = StorageDetailScreen(_make_storage(persistent=True))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'yes' appears in the Lifecycle section
    assert "yes" in content


def test_build_content_shows_persistent_no_when_false():
    # GIVEN a non-persistent storage entry
    screen = StorageDetailScreen(_make_storage(persistent=False))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'no' appears for Persistent
    assert "no" in content


def test_build_content_colours_alive_life():
    # GIVEN a storage entry with life='alive'
    screen = StorageDetailScreen(_make_storage(life="alive"))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'alive' appears with a colour markup tag
    assert "alive" in content
    assert "[" in content  # colour markup present


def test_build_content_colours_dying_life():
    # GIVEN a storage entry with life='dying'
    screen = StorageDetailScreen(_make_storage(life="dying"))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'dying' appears with a colour markup tag
    assert "dying" in content
    assert "[" in content


def test_build_content_colours_dead_life():
    # GIVEN a storage entry with life='dead'
    screen = StorageDetailScreen(_make_storage(life="dead"))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN 'dead' appears with a colour markup tag
    assert "dead" in content
    assert "[" in content


def test_build_content_shows_dash_for_empty_life():
    # GIVEN a storage entry with no life value
    screen = StorageDetailScreen(_make_storage(life=""))

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN a dash is shown for Life
    assert "—" in content


# ─────────────────────────────────────────────────────────────────────────────
# compose (integration — Textual pilot)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_storage_detail_screen_renders_panel(pilot):
    # GIVEN a StorageDetailScreen pushed onto the app
    storage = _make_storage()
    screen = StorageDetailScreen(storage)
    await pilot.app.push_screen(screen)
    await pilot.pause()

    # WHEN the screen is inspected
    panel = screen.query_one("#storage-detail-panel", Static)

    # THEN the panel exists and its border title contains the storage ID
    assert "data/0" in (panel.border_title or "")


def test_storage_detail_screen_shows_device_name_and_link():
    # GIVEN a block storage with device_name and device_link populated
    screen = StorageDetailScreen(
        _make_storage(device_name="sdb", device_link="/dev/disk/by-id/virtio-vol-abc123")
    )

    # WHEN the content is built
    content = screen._build_content()

    # THEN Device and Device Link rows are present
    assert "Device" in content
    assert "sdb" in content
    assert "Device Link" in content
    assert "/dev/disk/by-id/virtio-vol-abc123" in content


def test_storage_detail_screen_omits_device_rows_when_empty():
    # GIVEN a filesystem storage with no device info (Kubernetes/filesystem case)
    screen = StorageDetailScreen(_make_storage(device_name="", device_link=""))

    # WHEN the content is built
    content = screen._build_content()

    # THEN Device rows are absent
    assert "Device" not in content
