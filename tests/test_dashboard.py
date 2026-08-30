"""Tests for the dashboard config generation helpers (pure functions)."""

from __future__ import annotations

import json

from custom_components.veton.dashboard import (
    _find_entity,
    dashboard_target,
    generate_dashboard_config,
)


def test_dashboard_target_per_connector():
    # Connector 1 keeps the original URL for backward compatibility
    assert dashboard_target(1) == ("veton-charger", "Veton EV Charger")
    # Extra charging points get their own URL + title (no clobbering)
    assert dashboard_target(2) == ("veton-charger-2", "Veton EV Charger (Connector 2)")
    assert dashboard_target(3) == ("veton-charger-3", "Veton EV Charger (Connector 3)")


def test_find_entity_matches_domain_and_keywords():
    eids = [
        "sensor.veton_charging_power",
        "switch.veton_charging_enabled",
        "number.veton_max_charging_current",
    ]
    assert _find_entity(eids, "sensor", "charging_power") == "sensor.veton_charging_power"
    assert _find_entity(eids, "switch", "charging_enabled") == "switch.veton_charging_enabled"
    assert _find_entity(eids, "sensor", "charging_enabled") is None  # wrong domain
    assert _find_entity(eids, "sensor", "does_not_exist") is None


def test_generate_dashboard_is_single_charging_view():
    eids = [
        "sensor.veton_charging_power",
        "sensor.veton_session_energy",
        "sensor.veton_total_energy",
        "switch.veton_charging_enabled",
        "number.veton_max_charging_current",
    ]
    cfg = generate_dashboard_config(eids)

    assert list(cfg) == ["views"]
    assert len(cfg["views"]) == 1
    view = cfg["views"][0]
    assert view["path"] == "charging"
    assert view["cards"], "expected at least one card"

    blob = json.dumps(view)
    assert "sensor.veton_charging_power" in blob
    assert "number.veton_max_charging_current" in blob


def _controls_card(cfg: dict) -> dict:
    cards = cfg["views"][0]["cards"]
    return next(c for c in cards if c.get("title") == "Controls")


def test_controls_card_leads_with_max_current():
    eids = [
        "switch.veton_charging_enabled",
        "switch.veton_available",
        "number.veton_max_charging_current",
    ]
    rows = _controls_card(generate_dashboard_config(eids))["entities"]

    # Max Current works in every release mode, so it leads the card
    assert rows[0] == {"entity": "number.veton_max_charging_current", "name": "Max Current"}


def test_controls_switch_rows_are_conditional_on_availability():
    eids = [
        "switch.veton_charging_enabled",
        "switch.veton_available",
        "number.veton_max_charging_current",
    ]
    rows = _controls_card(generate_dashboard_config(eids))["entities"]

    # X300/X304 are only honoured in Modbus release mode; the switches report
    # themselves unavailable otherwise, so their rows are hidden.
    charging, available = rows[1], rows[2]

    assert charging["type"] == "conditional"
    assert charging["conditions"] == [
        {"entity": "switch.veton_charging_enabled", "state_not": "unavailable"}
    ]
    assert charging["row"] == {"entity": "switch.veton_charging_enabled", "name": "Charging"}

    assert available["type"] == "conditional"
    assert available["conditions"] == [
        {"entity": "switch.veton_available", "state_not": "unavailable"}
    ]
    assert available["row"] == {"entity": "switch.veton_available", "name": "Available"}


def test_controls_conditional_rows_still_use_find_placeholder():
    # No switch entities at all: _find still yields the placeholder, inside the
    # conditional row *and* its condition.
    rows = _controls_card(generate_dashboard_config(["number.veton_max_charging_current"]))["entities"]

    for row in rows[1:]:
        assert row["type"] == "conditional"
        assert row["conditions"][0]["entity"] == "switch.not_found"
        assert row["row"]["entity"] == "switch.not_found"
