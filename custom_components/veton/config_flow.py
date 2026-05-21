"""Config flow for the Veton EV Charger integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (
    CONF_CONNECTOR,
    DEFAULT_CONNECTOR,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    DOMAIN,
)
from .modbus_client import CharxModbusClient

_LOGGER = logging.getLogger(__name__)


def _entry_title(device_name: str, connector: int) -> str:
    """Entry/device title, suffixed with the connector for multi-CP chargers."""
    base = f"Veton Charger - {device_name}"
    return base if connector == DEFAULT_CONNECTOR else f"{base} (Connector {connector})"


def _connection_schema(
    host: str = "", port: int = DEFAULT_PORT, connector: int = DEFAULT_CONNECTOR
) -> vol.Schema:
    """Build the charger connection form schema with the given defaults."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host): str,
            vol.Required(CONF_PORT, default=port): int,
            vol.Required(CONF_CONNECTOR, default=connector): vol.All(
                int, vol.Range(min=1, max=8)
            ),
        }
    )


class VetonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Veton EV Charger."""

    VERSION = 1

    async def _test_connection(
        self, host: str, port: int, connector: int
    ) -> tuple[bool, str]:
        """Try to read the CHARX controller. Returns (success, device_name)."""
        client = CharxModbusClient(host, port, DEFAULT_SLAVE, connector)
        try:
            if not await client.connect():
                return False, ""
            global_data = await client.read_global_data()
            return True, global_data.device_name or f"CHARX ({host})"
        except Exception:  # noqa: BLE001 - any failure means "cannot connect"
            _LOGGER.debug("Could not reach CHARX at %s:%s", host, port, exc_info=True)
            return False, ""
        finally:
            await client.close()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the manual setup step (Settings > Add Integration)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            connector = user_input.get(CONF_CONNECTOR, DEFAULT_CONNECTOR)

            await self.async_set_unique_id(f"{host}:{port}:{connector}")
            self._abort_if_unique_id_configured()

            ok, device_name = await self._test_connection(host, port, connector)
            if ok:
                return self.async_create_entry(
                    title=_entry_title(device_name, connector),
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_CONNECTOR: connector,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to change the charger connection after setup."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            connector = user_input.get(CONF_CONNECTOR, DEFAULT_CONNECTOR)

            ok, _ = await self._test_connection(host, port, connector)
            if ok:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{host}:{port}:{connector}",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_CONNECTOR: connector,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(
                host=entry.data.get(CONF_HOST, ""),
                port=entry.data.get(CONF_PORT, DEFAULT_PORT),
                connector=entry.data.get(CONF_CONNECTOR, DEFAULT_CONNECTOR),
            ),
            errors=errors,
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle automatic import (used by the optional turnkey-Pi helper)."""
        host = import_data["host"]
        port = import_data.get("port", DEFAULT_PORT)
        connector = import_data.get("connector", DEFAULT_CONNECTOR)

        await self.async_set_unique_id(f"{host}:{port}:{connector}")
        self._abort_if_unique_id_configured()

        device_name = import_data.get("device_name", f"CHARX ({host})")
        return self.async_create_entry(
            title=_entry_title(device_name, connector),
            data={
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_CONNECTOR: connector,
            },
        )
