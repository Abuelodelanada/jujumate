"""Tests for MachineDetailScreen and its helpers."""

from datetime import datetime, timedelta, timezone

import pytest
from textual.widgets import Static

from jujumate.models.entities import MachineInfo, NetworkInterface
from jujumate.screens.machine_detail_screen import (
    MachineDetailScreen,
    _fmt_ts,
    _normalize_iso,
    _time_ago,
)

# ─────────────────────────────────────────────────────────────────────────────
# _time_ago
# ─────────────────────────────────────────────────────────────────────────────


def test_time_ago_empty_string_returns_empty():
    # GIVEN an empty string
    # WHEN _time_ago is called
    result = _time_ago("")
    # THEN an empty string is returned
    assert result == ""


def test_time_ago_returns_seconds():
    # GIVEN a timestamp 30 seconds ago
    ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN a seconds-ago string is returned
    assert result == "30s ago"


def test_time_ago_returns_minutes():
    # GIVEN a timestamp 90 seconds ago (1 minute)
    ts = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN a minutes-ago string is returned
    assert result == "1m ago"


def test_time_ago_returns_hours():
    # GIVEN a timestamp 7200 seconds ago (2 hours)
    ts = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN an hours-ago string is returned
    assert result == "2h ago"


def test_time_ago_returns_days():
    # GIVEN a timestamp 172800 seconds ago (2 days)
    ts = (datetime.now(timezone.utc) - timedelta(seconds=172800)).isoformat()
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN a days-ago string is returned
    assert result == "2d ago"


def test_time_ago_future_timestamp_returns_empty():
    # GIVEN a timestamp in the future
    ts = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN an empty string is returned (delta is negative)
    assert result == ""


def test_time_ago_naive_timestamp_is_treated_as_utc():
    # GIVEN an ISO timestamp without timezone info (naive datetime)
    ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%S")
    # WHEN _time_ago is called
    result = _time_ago(ts)
    # THEN it is treated as UTC and a valid relative string is returned
    assert result == "2m ago"


def test_time_ago_invalid_string_returns_input():
    # GIVEN a non-ISO string
    # WHEN _time_ago is called
    result = _time_ago("not-a-date")
    # THEN the original string is returned as fallback
    assert result == "not-a-date"


# ─────────────────────────────────────────────────────────────────────────────
# _normalize_iso
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_iso_replaces_z_with_offset():
    # GIVEN a timestamp with Z suffix
    # WHEN _normalize_iso is called
    result = _normalize_iso("2026-03-29T01:06:22.789123Z")
    # THEN Z is replaced with +00:00
    assert result == "2026-03-29T01:06:22.789123+00:00"


def test_normalize_iso_truncates_nanoseconds_to_microseconds():
    # GIVEN a timestamp with 9 fractional digits (nanoseconds)
    # WHEN _normalize_iso is called
    result = _normalize_iso("2026-03-29T01:06:22.789123456+00:00")
    # THEN fractional part is truncated to 6 digits
    assert result == "2026-03-29T01:06:22.789123+00:00"


def test_normalize_iso_handles_nanoseconds_and_z_together():
    # GIVEN a timestamp with both nanoseconds and Z suffix
    # WHEN _normalize_iso is called
    result = _normalize_iso("2026-03-29T01:06:22.789123456Z")
    # THEN both are normalized
    assert result == "2026-03-29T01:06:22.789123+00:00"


def test_normalize_iso_leaves_standard_format_unchanged():
    # GIVEN a standard ISO string with 6 decimals and offset
    ts = "2026-03-29T01:06:22.789123+00:00"
    # WHEN _normalize_iso is called
    result = _normalize_iso(ts)
    # THEN the string is unchanged
    assert result == ts


# ─────────────────────────────────────────────────────────────────────────────
# _fmt_ts
# ─────────────────────────────────────────────────────────────────────────────


def test_fmt_ts_empty_string_returns_empty():
    # GIVEN an empty string
    # WHEN _fmt_ts is called
    assert _fmt_ts("") == ""


def test_fmt_ts_formats_without_microseconds():
    # GIVEN an ISO timestamp with microseconds
    ts = "2024-06-01T12:34:56.789123+00:00"
    # WHEN _fmt_ts is called
    result = _fmt_ts(ts)
    # THEN the result is formatted as YYYY-MM-DD HH:MM:SS without microseconds
    assert result == "2024-06-01 12:34:56"


def test_fmt_ts_handles_naive_datetime():
    # GIVEN an ISO timestamp without timezone info
    ts = "2024-06-01T12:34:56"
    # WHEN _fmt_ts is called
    result = _fmt_ts(ts)
    # THEN it is formatted correctly
    assert result == "2024-06-01 12:34:56"


def test_fmt_ts_handles_nanoseconds():
    # GIVEN an ISO timestamp with nanosecond precision (from Juju's Go runtime)
    ts = "2026-03-29T01:06:22.789123456Z"
    # WHEN _fmt_ts is called
    result = _fmt_ts(ts)
    # THEN microseconds and Z suffix are handled correctly
    assert result == "2026-03-29 01:06:22"


def test_fmt_ts_invalid_string_returns_input():
    # GIVEN a non-ISO string
    # WHEN _fmt_ts is called
    result = _fmt_ts("not-a-date")
    # THEN the original string is returned as fallback
    assert result == "not-a-date"


# ─────────────────────────────────────────────────────────────────────────────
# MachineDetailScreen._build_content
# ─────────────────────────────────────────────────────────────────────────────


def test_machine_detail_screen_build_content_basic_info():
    # GIVEN a machine with basic fields
    machine = MachineInfo(
        model="dev",
        id="0",
        state="started",
        address="10.0.0.1",
        instance_id="i-abc123",
        base="ubuntu@22.04",
        az="us-east-1a",
        controller="ctrl",
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN all basic fields appear in the output
    assert "i-abc123" in content
    assert "10.0.0.1" in content
    assert "ubuntu@22.04" in content
    assert "us-east-1a" in content
    assert "ctrl" in content
    assert "dev" in content


def test_machine_detail_screen_build_content_hardware_section():
    # GIVEN a machine with hardware fields populated
    machine = MachineInfo(
        model="dev",
        id="1",
        state="started",
        address="10.0.0.2",
        instance_id="i-xyz789",
        base="ubuntu@22.04",
        az="",
        hardware_arch="amd64",
        hardware_cores=4,
        hardware_mem_mib=16384,
        hardware_disk_mib=51200,
        hardware_virt_type="kvm",
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the Hardware section appears with all hardware details
    assert "Hardware" in content
    assert "amd64" in content
    assert "4" in content
    assert "16384" in content
    assert "16.0 GiB" in content
    assert "51200" in content
    assert "50.0 GiB" in content
    assert "kvm" in content


def test_machine_detail_screen_build_content_no_hardware_section_when_empty():
    # GIVEN a machine with no hardware fields
    machine = MachineInfo(
        model="dev", id="2", state="started", address="", instance_id="", base="", az=""
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the Hardware section is absent
    assert "Hardware" not in content


def test_machine_detail_screen_build_content_network_interfaces():
    # GIVEN a machine with two network interfaces
    machine = MachineInfo(
        model="dev",
        id="3",
        state="started",
        address="10.0.0.3",
        instance_id="i-net",
        base="ubuntu@22.04",
        az="",
        network_interfaces=[
            NetworkInterface("eth0", ["10.0.0.3", "fe80::1"], "52:54:00:aa:bb:cc", "alpha"),
            NetworkInterface("eth1", ["192.168.1.1"], "52:54:00:dd:ee:ff", ""),
        ],
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the Network Interfaces section shows both interfaces with all IPs aligned
    assert "Network Interfaces" in content
    assert "eth0" in content
    assert "10.0.0.3" in content
    assert "fe80::1" in content
    assert "Space" in content
    assert "alpha" in content
    assert "eth1" in content
    assert "192.168.1.1" in content
    assert "fe80::1" in content


def test_machine_detail_screen_build_content_status_section_always_present():
    # GIVEN a machine with instance status, timestamps and message
    machine = MachineInfo(
        model="dev",
        id="4",
        state="started",
        address="",
        instance_id="",
        base="",
        az="",
        instance_status="running",
        message="ready",
        agent_since="2024-06-01T12:34:56.789123+00:00",
        instance_since="2024-06-01T11:00:00+00:00",
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN Status section appears with formatted timestamps (no microseconds)
    assert "Status" in content
    assert "started" in content
    assert "running" in content
    assert "ready" in content
    assert "2024-06-01 12:34:56" in content
    assert "2024-06-01 11:00:00" in content
    assert "789123" not in content


@pytest.mark.asyncio
async def test_machine_detail_screen_compose_sets_border_title(pilot):
    # GIVEN a MachineDetailScreen for machine "5"
    machine = MachineInfo(
        model="dev", id="5", state="started", address="", instance_id="", base="", az=""
    )
    screen = MachineDetailScreen(machine)

    # WHEN the screen is pushed onto the app
    await pilot.app.push_screen(screen)
    await pilot.pause()

    # THEN the panel's border_title includes the machine id
    panel = pilot.app.screen.query_one("#machine-detail-panel", Static)
    assert "5" in (panel.border_title or "")
