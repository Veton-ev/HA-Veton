"""Tests for the charging session state machine + persistence."""

from __future__ import annotations

from custom_components.veton.modbus_client import CharxConnectorData
from custom_components.veton.session_tracker import SessionTracker


def _frame(status: str, *, power_w: int = 0, rfid: str = "", energy_wh: int = 0,
           charging_time_s: int = 0) -> CharxConnectorData:
    return CharxConnectorData(
        vehicle_status=status,
        active_power_mw=power_w * 1000,
        rfid_uid=rfid,
        session_energy_wh=energy_wh,
        charging_time_s=charging_time_s,
    )


def _tracker(hass, tmp_path, name="entry") -> SessionTracker:
    """Tracker whose persistence file is isolated to this test's tmp dir."""
    tracker = SessionTracker(hass, name)
    tracker._storage_path = tmp_path / f"{name}.json"
    return tracker


async def test_full_session_lifecycle(hass, tmp_path):
    tracker = _tracker(hass, tmp_path)
    await tracker.load()

    # Plugged in, not charging yet
    await tracker.update(_frame("B2"))
    assert tracker.session_count == 0
    assert tracker.current_session is None

    # Charging starts (RFID captured at start)
    await tracker.update(_frame("C2", power_w=7000, rfid="CAFE"))
    assert tracker.current_session is not None
    assert tracker.current_session.rfid_uid == "CAFE"

    # Power climbs -> peak tracked
    await tracker.update(_frame("C2", power_w=11000, rfid="CAFE"))

    # Stops charging -> session recorded with end-of-session totals
    await tracker.update(_frame("B1", energy_wh=4200, charging_time_s=600))

    assert tracker.session_count == 1
    assert tracker.current_session is None
    session = tracker.sessions[0]
    assert session.rfid_uid == "CAFE"
    assert session.energy_wh == 4200
    assert session.duration_s == 600
    assert session.max_power_w == 11000
    assert session.started and session.ended


async def test_state_persists_across_reload(hass, tmp_path):
    tracker = _tracker(hass, tmp_path, "persist")
    await tracker.load()
    await tracker.update(_frame("C2", power_w=3000, rfid="A1"))
    await tracker.update(_frame("A1", energy_wh=1000, charging_time_s=120))
    assert tracker.session_count == 1

    # A fresh tracker pointed at the same file reloads from disk
    reloaded = _tracker(hass, tmp_path, "persist")
    await reloaded.load()
    assert reloaded.session_count == 1
    assert reloaded.sessions[0].energy_wh == 1000


async def test_two_sessions_get_distinct_ids(hass, tmp_path):
    tracker = _tracker(hass, tmp_path, "ids")
    await tracker.load()
    for _ in range(2):
        await tracker.update(_frame("C2", power_w=2000))
        await tracker.update(_frame("B1", energy_wh=500, charging_time_s=60))
    ids = [s.id for s in tracker.sessions]
    assert ids == [1, 2]


async def test_export_csv_has_header_and_rows(hass, tmp_path):
    tracker = _tracker(hass, tmp_path, "csv")
    await tracker.load()
    await tracker.update(_frame("C2", power_w=5000, rfid="DEAD"))
    await tracker.update(_frame("A1", energy_wh=2500, charging_time_s=300))

    csv_text = tracker.export_csv()
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("Session ID,Started")
    assert len(lines) == 2  # header + one session
    assert "DEAD" in lines[1]
    assert "2.5" in lines[1]  # 2500 Wh -> 2.5 kWh
