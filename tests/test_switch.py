"""Tests for the switch platform: release-mode gating of X300 / X304."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.veton.coordinator import CharxData
from custom_components.veton.modbus_client import CharxConnectorData, CharxGlobalData
from custom_components.veton.switch import (
    VetonAvailabilitySwitch,
    VetonChargeEnableSwitch,
)

RELEASE_OCPP = 4
RELEASE_MODBUS = 5


def _coordinator(release_mode: int | None, **connector_kwargs) -> MagicMock:
    """A coordinator stand-in with a single canned data snapshot.

    `release_mode=None` means the coordinator has no data yet.
    """
    coordinator = MagicMock()
    coordinator.last_update_success = True
    if release_mode is None:
        coordinator.data = None
    else:
        coordinator.data = CharxData(
            global_data=CharxGlobalData(device_name="My Charger"),
            connector_data=CharxConnectorData(
                release_mode=release_mode, **connector_kwargs
            ),
        )
    return coordinator


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "abc123"
    return entry


def _switches(coordinator: MagicMock):
    entry = _entry()
    return [
        VetonChargeEnableSwitch(coordinator, entry),
        VetonAvailabilitySwitch(coordinator, entry),
    ]


# ── Availability gating ─────────────────────────────────────────────


@pytest.mark.parametrize("mode", [0, 1, 2, 3, RELEASE_OCPP])
def test_switches_unavailable_outside_modbus_release_mode(mode):
    for switch in _switches(_coordinator(mode)):
        assert switch.available is False


def test_switches_available_in_modbus_release_mode():
    for switch in _switches(_coordinator(RELEASE_MODBUS)):
        assert switch.available is True


def test_switches_unavailable_without_coordinator_data():
    for switch in _switches(_coordinator(None)):
        assert switch.available is False
        assert switch.is_on is None


def test_switches_unavailable_when_coordinator_update_failed():
    coordinator = _coordinator(RELEASE_MODBUS)
    coordinator.last_update_success = False
    for switch in _switches(coordinator):
        assert switch.available is False


def test_is_on_reflects_registers_in_modbus_mode():
    coordinator = _coordinator(RELEASE_MODBUS, charge_enabled=True, availability=False)
    charge, availability = _switches(coordinator)
    assert charge.is_on is True
    assert availability.is_on is False


# ── Attributes ──────────────────────────────────────────────────────


def test_attributes_explain_inactive_switch_on_ocpp_charger():
    for switch in _switches(_coordinator(RELEASE_OCPP)):
        attrs = switch.extra_state_attributes
        assert attrs["release_mode"] == "OCPP"
        assert attrs["release_mode_value"] == RELEASE_OCPP
        assert "OCPP" in attrs["inactive_reason"]
        assert "Max charging current" in attrs["inactive_reason"]
    assert _switches(_coordinator(RELEASE_OCPP))[0].extra_state_attributes["register"] == "X300"
    assert _switches(_coordinator(RELEASE_OCPP))[1].extra_state_attributes["register"] == "X304"


def test_attributes_have_no_inactive_reason_in_modbus_mode():
    for switch in _switches(_coordinator(RELEASE_MODBUS)):
        attrs = switch.extra_state_attributes
        assert attrs["release_mode"] == "Modbus"
        assert "inactive_reason" not in attrs


def test_attributes_without_data():
    for switch in _switches(_coordinator(None)):
        attrs = switch.extra_state_attributes
        assert attrs["release_mode"] is None
        assert attrs["release_mode_value"] is None
        assert "inactive_reason" not in attrs


# ── Warning is logged once per entity ───────────────────────────────


def test_warning_logged_once_per_entity(caplog):
    coordinator = _coordinator(RELEASE_OCPP)
    charge, availability = _switches(coordinator)

    with caplog.at_level(logging.WARNING, logger="custom_components.veton.switch"):
        for _ in range(10):  # simulate repeated 5 s coordinator refreshes
            assert charge.available is False
            assert availability.available is False

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "custom_components.veton.switch"
    ]
    # One per entity, no matter how often availability is evaluated.
    assert len(warnings) == 2
    messages = [r.getMessage() for r in warnings]
    assert any("Charging enabled" in m and "X300" in m for m in messages)
    assert any("Available" in m and "X304" in m for m in messages)
    for message in messages:
        assert "OCPP" in message
        assert "Max charging current" in message


def test_no_warning_when_release_mode_is_modbus(caplog):
    with caplog.at_level(logging.WARNING, logger="custom_components.veton.switch"):
        for switch in _switches(_coordinator(RELEASE_MODBUS)):
            for _ in range(5):
                assert switch.available is True

    assert [
        r for r in caplog.records if r.name == "custom_components.veton.switch"
    ] == []


def test_no_warning_when_coordinator_has_no_data_yet(caplog):
    """A charger that hasn't reported yet is not a release-mode problem."""
    with caplog.at_level(logging.WARNING, logger="custom_components.veton.switch"):
        for switch in _switches(_coordinator(None)):
            assert switch.available is False

    assert [
        r for r in caplog.records if r.name == "custom_components.veton.switch"
    ] == []
