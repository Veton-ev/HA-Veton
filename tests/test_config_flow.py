"""Tests for the Veton EV Charger config + reconfigure flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.veton.const import CONF_CONNECTOR, DOMAIN
from custom_components.veton.modbus_client import CharxGlobalData

USER_INPUT = {CONF_HOST: "10.0.0.5", CONF_PORT: 502, CONF_CONNECTOR: 1}


def _mock_client(*, connect: bool = True, name: str = "Test Charger"):
    """Patch the config-flow Modbus client + skip real entry setup."""
    client_patch = patch("custom_components.veton.config_flow.CharxModbusClient")
    setup_patch = patch(
        "custom_components.veton.async_setup_entry",
        new_callable=AsyncMock,
        return_value=True,
    )
    return client_patch, setup_patch, connect, name


def _configure_mock(cls, connect, name):
    inst = cls.return_value
    inst.connect = AsyncMock(return_value=connect)
    inst.read_global_data = AsyncMock(return_value=CharxGlobalData(device_name=name))
    inst.close = AsyncMock()
    return inst


async def test_user_flow_success(hass):
    client_patch, setup_patch, connect, name = _mock_client()
    with client_patch as cls, setup_patch:
        _configure_mock(cls, connect, name)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Veton Charger - Test Charger"
    assert result2["data"] == USER_INPUT
    assert result2["result"].unique_id == "10.0.0.5:502:1"


async def test_user_flow_cannot_connect(hass):
    client_patch, setup_patch, _, name = _mock_client(connect=False)
    with client_patch as cls, setup_patch:
        _configure_mock(cls, False, name)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.5:502:1", data=USER_INPUT
    ).add_to_hass(hass)

    client_patch, setup_patch, connect, name = _mock_client()
    with client_patch as cls, setup_patch:
        _configure_mock(cls, connect, name)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reconfigure_updates_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="10.0.0.5:502:1", data=USER_INPUT
    )
    entry.add_to_hass(hass)

    client_patch, setup_patch, connect, name = _mock_client()
    with client_patch as cls, setup_patch:
        _configure_mock(cls, connect, name)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "10.0.0.99", CONF_PORT: 502, CONF_CONNECTOR: 1},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.data[CONF_HOST] == "10.0.0.99"
    assert updated.unique_id == "10.0.0.99:502:1"


async def test_import_flow_creates_entry(hass):
    _, setup_patch, _, _ = _mock_client()
    with setup_patch:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={"host": "10.0.0.9", "port": 502, "connector": 1, "device_name": "Imp"},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Veton Charger - Imp"
    assert result["data"] == {CONF_HOST: "10.0.0.9", CONF_PORT: 502, CONF_CONNECTOR: 1}
