"""Auto-provisioned Lovelace dashboard for Veton EV Charger.

Creates a dedicated "Veton" dashboard in the HA sidebar on first setup.
Uses HA's internal Lovelace + frontend APIs so the dashboard appears
immediately without requiring a restart.
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
    """Generate a Lovelace dashboard config using discovered entity IDs."""

    has_p1 = any("mains_meter" in e for e in entity_ids)
    has_tariffs = any("electricity_price" in e and "sensor." in e for e in entity_ids)
    has_ems = any("ems_status" in e for e in entity_ids)

    # ── View 1: Charging ─────────────────────────────────────────
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

    # ── View 2: Energy Management ────────────────────────────────
    ems_cards: list[dict] = [
        {
            "type": "markdown",
            "content": "# ☀️ Energy Management",
        },
    ]

    if has_ems:
        ems_cards.extend([
            {
                "type": "entities",
                "title": "EMS Control",
                "state_color": True,
                "entities": [
                    {"entity": _find(entity_ids, "select", "charging_mode"), "name": "Charging Mode", "icon": "mdi:tune"},
                    {"entity": _find(entity_ids, "sensor", "ems_status"), "name": "EMS Status", "icon": "mdi:information-outline"},
                    {"entity": _find(entity_ids, "sensor", "ems_charging_active"), "name": "EMS Charging", "icon": "mdi:ev-station"},
                    {"entity": _find(entity_ids, "sensor", "ems_target_current"), "name": "Target Current", "icon": "mdi:current-ac"},
                ],
            },
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "gauge",
                        "entity": _find(entity_ids, "sensor", "ems_solar_surplus"),
                        "name": "Solar Surplus",
                        "unit": "W",
                        "min": -5000,
                        "max": 10000,
                        "severity": {"green": 1400, "yellow": 0, "red": -5000},
                    },
                    {
                        "type": "gauge",
                        "entity": _find(entity_ids, "sensor", "ems_available_site_current"),
                        "name": "Site Headroom",
                        "unit": "A",
                        "min": 0,
                        "max": 40,
                        "severity": {"green": 16, "yellow": 6, "red": 0},
                    },
                ],
            },
            {
                "type": "entities",
                "title": "EMS Settings",
                "entities": [
                    {"entity": _find(entity_ids, "number", "ems_max_site_current"), "name": "Max Site Current (fuse)"},
                    {"entity": _find(entity_ids, "number", "ems_max_charger_current"), "name": "Max Charger Current"},
                    {"entity": _find(entity_ids, "number", "ems_min_solar_surplus"), "name": "Min Solar Surplus"},
                    {"entity": _find(entity_ids, "number", "ems_solar_margin"), "name": "Solar Margin"},
                    {"entity": _find(entity_ids, "number", "ems_cheap_hours"), "name": "Cheap Hours"},
                ],
            },
        ])

    if has_p1:
        ems_cards.extend([
            {
                "type": "history-graph",
                "title": "Power (24h)",
                "hours_to_show": 24,
                "entities": [
                    {"entity": _find(entity_ids, "sensor", "grid_power_l1"), "name": "Grid"},
                    {"entity": _find(entity_ids, "sensor", "charging_power"), "name": "Charger"},
                ],
            },
            {
                "type": "glance",
                "title": "Grid Meter (P1)",
                "columns": 3,
                "entities": [
                    {"entity": _find(entity_ids, "sensor", "mains", "grid_power_l1"), "name": "L1"},
                    {"entity": _find(entity_ids, "sensor", "mains", "grid_power_l2"), "name": "L2"},
                    {"entity": _find(entity_ids, "sensor", "mains", "grid_power_l3"), "name": "L3"},
                ],
            },
            {
                "type": "entities",
                "title": "Grid Totals",
                "entities": [
                    {"entity": _find(entity_ids, "sensor", "grid_total_import"), "name": "Total Import", "icon": "mdi:transmission-tower-import"},
                    {"entity": _find(entity_ids, "sensor", "grid_total_export"), "name": "Total Export", "icon": "mdi:transmission-tower-export"},
                    {"entity": _find(entity_ids, "sensor", "grid_peak_demand"), "name": "Peak Demand", "icon": "mdi:chart-bell-curve"},
                ],
            },
        ])

    if not has_ems and not has_p1:
        ems_cards.append({
            "type": "markdown",
            "content": (
                "**No P1 meter configured.**\n\n"
                "Add a HomeWizard P1 meter to enable solar charging, "
                "capacity limitation, and peak shaving."
            ),
        })

    # ── View 3: Tariffs ──────────────────────────────────────────
    tariff_cards: list[dict] = [
        {
            "type": "markdown",
            "content": "# 💰 Electricity Prices",
        },
    ]

    if has_tariffs:
        tariff_cards.extend([
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "entity",
                        "entity": _find(entity_ids, "sensor", "electricity_price_today_min"),
                        "name": "Today Min",
                    },
                    {
                        "type": "entity",
                        "entity": _find(entity_ids, "sensor", "electricity_price_today_avg"),
                        "name": "Today Avg",
                    },
                    {
                        "type": "entity",
                        "entity": _find(entity_ids, "sensor", "electricity_price_today_max"),
                        "name": "Today Max",
                    },
                ],
            },
            {
                "type": "entities",
                "title": "Tariff Status",
                "state_color": True,
                "entities": [
                    {"entity": _find(entity_ids, "sensor", "electricity_price", "today_min"), "name": "Current Price", "icon": "mdi:currency-eur"},
                    {"entity": _find(entity_ids, "sensor", "price_is_cheap"), "name": "Is Cheap Now?", "icon": "mdi:cash-check"},
                    {"entity": _find(entity_ids, "sensor", "tomorrow_prices"), "name": "Tomorrow Available", "icon": "mdi:calendar-arrow-right"},
                ],
            },
            {
                "type": "history-graph",
                "title": "Electricity Price (48h)",
                "hours_to_show": 48,
                "entities": [
                    {"entity": _find(entity_ids, "sensor", "electricity_price_today_avg"), "name": "Price"},
                ],
            },
        ])
    else:
        tariff_cards.append({
            "type": "markdown",
            "content": "**Tariff data not available.** Check your internet connection.",
        })

    views = [
        {"title": "Charging", "path": "charging", "icon": "mdi:ev-station", "cards": charging_cards},
        {"title": "Energy", "path": "energy", "icon": "mdi:solar-power-variant", "cards": ems_cards},
        {"title": "Tariffs", "path": "tariffs", "icon": "mdi:currency-eur", "cards": tariff_cards},
    ]

    return {"views": views}


async def async_create_dashboard(
    hass: HomeAssistant, entity_ids: list[str]
) -> None:
    """Create or update the Veton dashboard using HA's internal APIs.

    Strategy:
    1. Use DashboardsCollection to register the dashboard (persisted via HA's Store)
    2. Register frontend panel for sidebar entry
    3. Create LovelaceStorage and save content (fires EVENT_LOVELACE_UPDATED)
    4. Also update the default Overview dashboard
    5. Set default_panel via frontend system store
    """
    try:
        config = generate_dashboard_config(entity_ids)
        await _create_dashboard_via_collection(hass, config)
        await _update_default_overview(hass, config)
        await _set_default_panel(hass)
        _LOGGER.info(
            "Veton dashboard created with %d entities", len(entity_ids)
        )
    except Exception as err:
        _LOGGER.warning(
            "Could not auto-create dashboard (non-critical): %s",
            err,
            exc_info=True,
        )


async def _create_dashboard_via_collection(
    hass: HomeAssistant, config: dict
) -> None:
    """Create dashboard using HA's DashboardsCollection + panel APIs."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.components.lovelace.dashboard import (
        DashboardsCollection,
        LovelaceStorage,
    )

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.warning("Lovelace not loaded yet, skipping dashboard creation")
        return

    # Skip if dashboard already exists
    if DASHBOARD_URL in lovelace_data.dashboards:
        _LOGGER.debug("Veton dashboard already exists, updating content")
        await lovelace_data.dashboards[DASHBOARD_URL].async_save(config)
        return

    # Step 1: Persist the dashboard via a DashboardsCollection
    # (uses HA's own Store, so it won't be overwritten by HA's saves)
    coll = DashboardsCollection(hass)
    await coll.async_load()

    # Check it's not already in the collection
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
    lovelace_data.dashboards[DASHBOARD_URL] = LovelaceStorage(
        hass, dashboard_info
    )
    await lovelace_data.dashboards[DASHBOARD_URL].async_save(config)


async def _update_default_overview(
    hass: HomeAssistant, config: dict
) -> None:
    """Update the default Overview dashboard with Veton content."""
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        return

    # The default Overview is stored under key None
    default_dashboard = lovelace_data.dashboards.get(None)
    if default_dashboard is not None:
        try:
            await default_dashboard.async_save(config)
            _LOGGER.debug("Updated default Overview with Veton dashboard")
        except Exception:
            _LOGGER.debug("Could not update default Overview")


async def _set_default_panel(hass: HomeAssistant) -> None:
    """Set the Veton dashboard as the default panel via HA's frontend store."""
    try:
        store = await frontend.async_system_store(hass)
        core_data = store.data.get("core") or {}
        await store.async_set_item(
            "core",
            {**core_data, "default_panel": f"lovelace-{DASHBOARD_URL}"},
        )
        _LOGGER.debug("Set default panel to lovelace-%s", DASHBOARD_URL)
    except Exception as err:
        _LOGGER.debug(
            "Could not set default panel via system store: %s", err
        )
