"""Veton EV Charger integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from .const import (
    CONF_CONNECTOR,
    CONF_P1_ENABLED,
    CONF_P1_HOST,
    CONF_TARIFF_ENABLED,
    DEFAULT_CONNECTOR,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    DOMAIN,
)
from .coordinator import VetonCoordinator
from .ems import EmsController, EmsSettings
from .modbus_client import CharxModbusClient
from .p1_client import P1Client
from .session_tracker import SessionTracker
from .dashboard import async_create_dashboard
from .tariff_client import TariffClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Veton component.

    If no config entries exist yet (fresh install), register a listener
    that triggers the config flow after HA is fully started + onboarded.
    """
    from .first_boot import async_register
    async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Veton EV Charger from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    connector = entry.data.get(CONF_CONNECTOR, DEFAULT_CONNECTOR)

    # Connect to CHARX controller
    client = CharxModbusClient(host, port, DEFAULT_SLAVE, connector)
    connected = await client.connect()
    if not connected:
        _LOGGER.error("Failed to connect to CHARX at %s:%s", host, port)
        return False

    # Set up watchdog: 30s timeout, fallback to 6A (minimum)
    try:
        await client.set_watchdog(fallback_current_a=6, timeout_s=30)
    except Exception:
        _LOGGER.warning("Could not set watchdog, continuing without it")

    # Connect to P1 meter if configured
    p1_client: P1Client | None = None
    if entry.data.get(CONF_P1_ENABLED) and entry.data.get(CONF_P1_HOST):
        p1_client = P1Client(entry.data[CONF_P1_HOST])
        if not await p1_client.test_connection():
            _LOGGER.warning(
                "P1 meter at %s not reachable, continuing without it",
                entry.data[CONF_P1_HOST],
            )
            p1_client = None

    # Create tariff client if enabled
    tariff_client: TariffClient | None = None
    if entry.data.get(CONF_TARIFF_ENABLED, True):  # enabled by default
        tariff_client = TariffClient()

    # Create EMS controller (only useful with P1 meter data)
    ems: EmsController | None = None
    if p1_client:
        ems = EmsController(EmsSettings())

    session_tracker = SessionTracker(hass, entry.entry_id)

    coordinator = VetonCoordinator(
        hass, client, session_tracker, p1_client, ems, tariff_client
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "p1_client": p1_client,
        "tariff_client": tariff_client,
        "ems": ems,
        "session_tracker": session_tracker,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (once for the domain)
    if not hass.services.has_service(DOMAIN, "export_sessions_csv"):
        async def handle_export_csv(call: ServiceCall) -> ServiceResponse:
            """Export charging sessions as CSV."""
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                tracker = hass.data[DOMAIN][entry_id]["session_tracker"]
            else:
                first_key = next(iter(hass.data[DOMAIN]))
                tracker = hass.data[DOMAIN][first_key]["session_tracker"]
            csv_data = tracker.export_csv()
            return {"csv": csv_data}

        hass.services.async_register(
            DOMAIN,
            "export_sessions_csv",
            handle_export_csv,
            supports_response=SupportsResponse.ONLY,
        )

    # Auto-create branded dashboard using real entity IDs from the registry
    from homeassistant.helpers import entity_registry as er
    ent_reg = er.async_get(hass)
    entity_ids = [
        ent.entity_id
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    ]
    await async_create_dashboard(hass, entity_ids)

    # Watchdog refresh: keep alive every coordinator update
    def _watchdog_refresh() -> None:
        hass.async_create_task(
            _watchdog_do_refresh(), "veton_watchdog_refresh"
        )

    async def _watchdog_do_refresh() -> None:
        try:
            await client.refresh_watchdog(30)
        except Exception:
            _LOGGER.debug("Watchdog refresh failed, will retry next cycle")

    entry.async_on_unload(
        coordinator.async_add_listener(_watchdog_refresh)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].close()
        if data.get("p1_client"):
            await data["p1_client"].close()
        if data.get("tariff_client"):
            await data["tariff_client"].close()
    return unload_ok
