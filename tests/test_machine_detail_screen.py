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


@pytest.mark.parametrize("func", [_time_ago, _fmt_ts], ids=["_time_ago", "_fmt_ts"])
def test_empty_string_returns_empty(func):
    # GIVEN an empty string
    # WHEN the function is called
    result = func("")
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


@pytest.mark.parametrize("func", [_time_ago, _fmt_ts], ids=["_time_ago", "_fmt_ts"])
def test_invalid_string_returns_input(func):
    # GIVEN a non-ISO string
    # WHEN the function is called
    result = func("not-a-date")
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


def test_machine_detail_screen_build_content_network_interface_with_no_ips():
    # GIVEN a machine with a network interface that has no IP addresses assigned
    machine = MachineInfo(
        model="dev",
        id="3b",
        state="started",
        address="",
        instance_id="",
        base="",
        az="",
        network_interfaces=[
            NetworkInterface("eth0", [], "52:54:00:aa:bb:cc", ""),
        ],
    )
    screen = MachineDetailScreen(machine)

    # WHEN _build_content is called
    content = screen._build_content()

    # THEN the IPs row shows a dash placeholder
    assert "eth0" in content
    assert "IPs" in content
    assert "—" in content


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


# ─────────────────────────────────────────────────────────────────────────────
# Individual section methods
# ─────────────────────────────────────────────────────────────────────────────


def _minimal_machine(**kwargs: object) -> MachineInfo:
    defaults = dict(model="m", id="0", state="started", address="", instance_id="", base="", az="")
    defaults.update(kwargs)
    return MachineInfo(**defaults)  # type: ignore[arg-type]


def test_section_meta_returns_all_six_rows():
    # GIVEN a machine with all meta fields populated
    machine = _minimal_machine(
        instance_id="i-abc",
        address="10.0.0.1",
        base="ubuntu@22.04",
        az="us-east-1a",
        controller="ctrl",
        model="prod",
    )
    # WHEN _section_meta is called
    lines = MachineDetailScreen(machine)._section_meta()
    joined = "\n".join(lines)
    # THEN all six fields appear
    assert "i-abc" in joined
    assert "10.0.0.1" in joined
    assert "ubuntu@22.04" in joined
    assert "us-east-1a" in joined
    assert "ctrl" in joined
    assert "prod" in joined


def test_section_meta_uses_dash_for_missing_fields():
    # GIVEN a machine with no optional meta fields
    machine = _minimal_machine()
    # WHEN _section_meta is called
    lines = MachineDetailScreen(machine)._section_meta()
    joined = "\n".join(lines)
    # THEN missing fields are shown as —
    assert "—" in joined


def test_section_hardware_returns_empty_when_no_hardware():
    # GIVEN a machine with no hardware fields
    machine = _minimal_machine()
    # WHEN _section_hardware is called
    lines = MachineDetailScreen(machine)._section_hardware()
    # THEN an empty list is returned
    assert lines == []


def test_section_hardware_includes_all_fields():
    # GIVEN a machine with all hardware fields
    machine = _minimal_machine(
        hardware_arch="amd64",
        hardware_cores=8,
        hardware_mem_mib=8192,
        hardware_disk_mib=20480,
        hardware_virt_type="kvm",
    )
    # WHEN _section_hardware is called
    lines = MachineDetailScreen(machine)._section_hardware()
    joined = "\n".join(lines)
    # THEN all fields and the section title appear
    assert "Hardware" in joined
    assert "amd64" in joined
    assert "8" in joined
    assert "8192" in joined
    assert "8.0 GiB" in joined
    assert "20480" in joined
    assert "kvm" in joined


def test_section_status_includes_agent_and_instance():
    # GIVEN a machine with agent/instance status and timestamps
    machine = _minimal_machine(
        state="started",
        instance_status="running",
        agent_since="2024-06-01T12:00:00+00:00",
        instance_since="2024-06-01T11:00:00+00:00",
    )
    # WHEN _section_status is called
    lines = MachineDetailScreen(machine)._section_status()
    joined = "\n".join(lines)
    # THEN Status section contains both rows with formatted timestamps
    assert "Status" in joined
    assert "started" in joined
    assert "running" in joined
    assert "2024-06-01 12:00:00" in joined
    assert "2024-06-01 11:00:00" in joined


def test_section_status_omits_message_row_when_empty():
    # GIVEN a machine with no message
    machine = _minimal_machine(state="started")
    # WHEN _section_status is called
    lines = MachineDetailScreen(machine)._section_status()
    joined = "\n".join(lines)
    # THEN no Message row appears
    assert "Message" not in joined


def test_section_status_includes_message_when_set():
    # GIVEN a machine with a workload message
    machine = _minimal_machine(state="started", message="hook failed")
    # WHEN _section_status is called
    lines = MachineDetailScreen(machine)._section_status()
    joined = "\n".join(lines)
    # THEN the Message row appears with the message text
    assert "Message" in joined
    assert "hook failed" in joined


def test_section_network_returns_empty_when_no_interfaces():
    # GIVEN a machine with no network interfaces
    machine = _minimal_machine()
    # WHEN _section_network is called
    lines = MachineDetailScreen(machine)._section_network()
    # THEN an empty list is returned
    assert lines == []


def test_section_network_renders_all_interface_fields():
    # GIVEN a machine with one full interface
    machine = _minimal_machine(
        network_interfaces=[NetworkInterface("eth0", ["10.0.0.1", "fe80::1"], "aa:bb:cc", "alpha")]
    )
    # WHEN _section_network is called
    lines = MachineDetailScreen(machine)._section_network()
    joined = "\n".join(lines)
    # THEN all interface details appear
    assert "Network Interfaces" in joined
    assert "eth0" in joined
    assert "10.0.0.1" in joined
    assert "fe80::1" in joined
    assert "aa:bb:cc" in joined
    assert "alpha" in joined


def test_render_section_produces_title_separator_and_rows():
    # GIVEN a section with two rows
    machine = _minimal_machine()
    screen = MachineDetailScreen(machine)
    # WHEN _render_section is called
    lines = screen._render_section("My Section", [("Label", "value"), ("Other", "data")])
    joined = "\n".join(lines)
    # THEN the title, separator and both rows appear
    assert "My Section" in joined
    assert "─" in joined
    assert "Label" in joined
    assert "value" in joined
    assert "Other" in joined
    assert "data" in joined
