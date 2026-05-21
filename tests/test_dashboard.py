"""Tests for the dashboard config generation helpers (pure functions)."""

from __future__ import annotations

import json

from custom_components.veton.dashboard import _find_entity, generate_dashboard_config


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
