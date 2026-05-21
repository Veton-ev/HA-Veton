"""Auto-provisioned Lovelace dashboard for Veton EV Charger.

Creates a dedicated "Veton EV Charger" dashboard in the HA sidebar on first
setup, using HA's internal Lovelace + frontend APIs so it appears without a
restart. It is added as a *separate* sidebar entry only — we never touch the
user's default Overview dashboard or their default_panel.
"""

from __future__ import annotations

import logging

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL = "veton-charger"
DASHBOARD_TITLE = "Veton EV Charger"
DASHBOARD_ICON = "mdi:ev-station"


def _find_entity(
    entity_ids: list[str], domain: str, *keywords: str
) -> str | None:
    """Find an entity ID by domain and keywords in the suffix."""
    for eid in entity_ids:
        if not eid.startswith(f"{domain}."):
            continue
        suffix = eid.lower()
        if all(kw in suffix for kw in keywords):
            return eid
    return None


def _find(entities: list[str], domain: str, *kw: str) -> str:
    """Find entity or return placeholder."""
    return _find_entity(entities, domain, *kw) or f"{domain}.not_found"


def generate_dashboard_config(entity_ids: list[str]) -> dict:
    """Generate a single-view Lovelace dashboard for the charger."""
    charging_cards: list[dict] = [
        {
            "type": "markdown",
            "content": "# ⚡ Veton EV Charger",
        },
        {
            "type": "entities",
            "title": "Live Status",
            "state_color": True,
            "entities": [
                {"entity": _find(entity_ids, "sensor", "vehicle_status_code"), "name": "Vehicle Status", "icon": "mdi:car-electric"},
                {"entity": _find(entity_ids, "sensor", "charging_power"), "name": "Charging Power", "icon": "mdi:flash"},
                {"entity": _find(entity_ids, "sensor", "session_energy"), "name": "Session Energy", "icon": "mdi:battery-charging"},
                {"entity": _find(entity_ids, "sensor", "total_energy"), "name": "Total Energy", "icon": "mdi:counter"},
            ],
        },
        {
            "type": "entities",
            "title": "Controls",
            "show_header_toggle": False,
            "entities": [
                {"entity": _find(entity_ids, "switch", "charging_enabled"), "name": "Charging"},
                {"entity": _find(entity_ids, "switch", "available"), "name": "Available"},
                {"entity": _find(entity_ids, "number", "max_charging_current"), "name": "Max Current"},
            ],
        },
        {
            "type": "glance",
            "title": "Phase Voltages",
            "columns": 3,
            "entities": [
                {"entity": _find(entity_ids, "sensor", "voltage_l1"), "name": "L1"},
                {"entity": _find(entity_ids, "sensor", "voltage_l2"), "name": "L2"},
                {"entity": _find(entity_ids, "sensor", "voltage_l3"), "name": "L3"},
            ],
        },
        {
            "type": "glance",
            "title": "Phase Currents",
            "columns": 3,
            "entities": [
                {"entity": _find(entity_ids, "sensor", "current_l1"), "name": "L1"},
                {"entity": _find(entity_ids, "sensor", "current_l2"), "name": "L2"},
                {"entity": _find(entity_ids, "sensor", "current_l3"), "name": "L3"},
            ],
        },
        {
            "type": "history-graph",
            "title": "Charging Power (24h)",
            "hours_to_show": 24,
            "entities": [
                {"entity": _find(entity_ids, "sensor", "charging_power"), "name": "Power"},
            ],
        },
        {
            "type": "entities",
            "title": "Session Info",
            "entities": [
                {"entity": _find(entity_ids, "sensor", "last_rfid"), "name": "Last RFID", "icon": "mdi:card-account-details"},
                {"entity": _find(entity_ids, "sensor", "connection_time"), "name": "Connection Time", "icon": "mdi:timer-outline"},
                {"entity": _find(entity_ids, "sensor", "charging_time"), "name": "Charging Time", "icon": "mdi:timer"},
                {"entity": _find(entity_ids, "sensor", "total_sessions"), "name": "Total Sessions", "icon": "mdi:history"},
                {"entity": _find(entity_ids, "sensor", "error_code"), "name": "Error Code", "icon": "mdi:alert-circle-outline"},
            ],
        },
    ]

    return {
        "views": [
            {
                "title": "Charging",
                "path": "charging",
                "icon": "mdi:ev-station",
                "cards": charging_cards,
            },
        ]
    }


async def async_create_dashboard(
    hass: HomeAssistant, entity_ids: list[str]
) -> None:
    """Create or update the Veton sidebar dashboard via HA's internal APIs."""
    try:
        config = generate_dashboard_config(entity_ids)
        await _create_dashboard_via_collection(hass, config)
        _LOGGER.info("Veton dashboard created with %d entities", len(entity_ids))
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not auto-create dashboard (non-critical): %s", err, exc_info=True
        )


async def _create_dashboard_via_collection(
    hass: HomeAssistant, config: dict
) -> None:
    """Create the dashboard using HA's DashboardsCollection + panel APIs."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.components.lovelace.dashboard import (
        DashboardsCollection,
        LovelaceStorage,
    )

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning("Lovelace not loaded yet, skipping dashboard creation")
        return

    # If the dashboard already exists, just refresh its content
    if DASHBOARD_URL in lovelace_data.dashboards:
        _LOGGER.debug("Veton dashboard already exists, updating content")
        await lovelace_data.dashboards[DASHBOARD_URL].async_save(config)
        return

    # Step 1: Persist the dashboard via a DashboardsCollection (HA's own Store)
    coll = DashboardsCollection(hass)
    await coll.async_load()

    existing = [i for i in coll.async_items() if i.get("url_path") == DASHBOARD_URL]
    if not existing:
        await coll.async_create_item({
            "url_path": DASHBOARD_URL,
            "title": DASHBOARD_TITLE,
            "icon": DASHBOARD_ICON,
            "show_in_sidebar": True,
            "require_admin": False,
        })

    # Step 2: Register the frontend panel (sidebar entry)
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL,
            config={"mode": "storage"},
            require_admin=False,
            update=False,
        )
    except ValueError:
        _LOGGER.debug("Panel %s already registered", DASHBOARD_URL)

    # Step 3: Create LovelaceStorage in hass.data and save content
    dashboard_info = {
        "id": DASHBOARD_URL,
        "url_path": DASHBOARD_URL,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "mode": "storage",
        "require_admin": False,
        "show_in_sidebar": True,
    }
    lovelace_data.dashboards[DASHBOARD_URL] = LovelaceStorage(hass, dashboard_info)
    await lovelace_data.dashboards[DASHBOARD_URL].async_save(config)
