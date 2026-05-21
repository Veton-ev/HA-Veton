"""Veton EV Charger integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from .const import CONF_CONNECTOR, DEFAULT_CONNECTOR, DEFAULT_PORT, DEFAULT_SLAVE, DOMAIN
from .coordinator import VetonCoordinator
from .dashboard import async_create_dashboard
from .modbus_client import CharxModbusClient
from .session_tracker import SessionTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Veton EV Charger from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    connector = entry.data.get(CONF_CONNECTOR, DEFAULT_CONNECTOR)

    # Connect to the CHARX controller
    client = CharxModbusClient(host, port, DEFAULT_SLAVE, connector)
    if not await client.connect():
        _LOGGER.error("Failed to connect to CHARX at %s:%s", host, port)
        return False

    # Safety watchdog: if HA stops talking to the charger for 30s, fall back
    # to the minimum current (6A) rather than holding the last setpoint.
    try:
        await client.set_watchdog(fallback_current_a=6, timeout_s=30)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Could not set watchdog, continuing without it")

    session_tracker = SessionTracker(hass, entry.entry_id)
    coordinator = VetonCoordinator(hass, client, session_tracker)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "session_tracker": session_tracker,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the CSV export service once for the domain
    if not hass.services.has_service(DOMAIN, "export_sessions_csv"):

        async def handle_export_csv(call: ServiceCall) -> ServiceResponse:
            """Export charging sessions as CSV."""
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                tracker = hass.data[DOMAIN][entry_id]["session_tracker"]
            else:
                first_key = next(iter(hass.data[DOMAIN]))
                tracker = hass.data[DOMAIN][first_key]["session_tracker"]
            return {"csv": tracker.export_csv()}

        hass.services.async_register(
            DOMAIN,
            "export_sessions_csv",
            handle_export_csv,
            supports_response=SupportsResponse.ONLY,
        )

    # Provision a dedicated "Veton EV Charger" dashboard in the sidebar.
    # This never overrides the user's existing default dashboard.
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    entity_ids = [
        ent.entity_id
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    ]
    await async_create_dashboard(hass, entity_ids)

    # Keep the charger watchdog alive on every coordinator update
    async def _watchdog_do_refresh() -> None:
        try:
            await client.refresh_watchdog(30)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Watchdog refresh failed, will retry next cycle")

    def _watchdog_refresh() -> None:
        hass.async_create_task(_watchdog_do_refresh(), "veton_watchdog_refresh")

    entry.async_on_unload(coordinator.async_add_listener(_watchdog_refresh))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].close()
    return unload_ok
