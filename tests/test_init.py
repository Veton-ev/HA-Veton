"""End-to-end setup/unload test with a mocked Modbus client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.veton.const import CONF_CONNECTOR, DOMAIN
from custom_components.veton.modbus_client import CharxConnectorData, CharxGlobalData


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    client.close = AsyncMock()
    client.set_watchdog = AsyncMock()
    client.refresh_watchdog = AsyncMock()
    client.read_global_data = AsyncMock(
        return_value=CharxGlobalData(device_name="My Charger", software_version="1.9")
    )
    client.read_connector_data = AsyncMock(
        return_value=CharxConnectorData(
            vehicle_status="B2", max_current_a=16, max_current_setting=32
        )
    )
    return client


async def test_setup_creates_entities_and_unload_cleans_up(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Charger",
        unique_id="10.0.0.5:502:1",
        data={CONF_HOST: "10.0.0.5", CONF_PORT: 502, CONF_CONNECTOR: 1},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.veton.CharxModbusClient", return_value=_fake_client()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # The coordinator has live data
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        assert coordinator.data.connector_data.vehicle_status == "B2"
        assert coordinator.data.global_data.device_name == "My Charger"

        # Entities registered across sensor/switch/number platforms
        ent_reg = er.async_get(hass)
        entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        domains = {e.domain for e in entities}
        assert {"sensor", "switch", "number"} <= domains
        assert len(entities) >= 20

        # The CSV export service is registered
        assert hass.services.has_service(DOMAIN, "export_sessions_csv")

    # Unload tears everything down
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "export_sessions_csv")
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
