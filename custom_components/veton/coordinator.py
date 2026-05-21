"""Data update coordinator for Veton EV Charger."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.exceptions import ModbusException

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .modbus_client import CharxConnectorData, CharxGlobalData, CharxModbusClient
from .session_tracker import SessionTracker

_LOGGER = logging.getLogger(__name__)


@dataclass
class CharxData:
    """Combined data read from the CHARX controller."""

    global_data: CharxGlobalData
    connector_data: CharxConnectorData


class VetonCoordinator(DataUpdateCoordinator[CharxData]):
    """Coordinator that polls the CHARX controller over Modbus/TCP."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CharxModbusClient,
        session_tracker: SessionTracker,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.session_tracker = session_tracker
        self._global_data: CharxGlobalData | None = None

    async def _async_update_data(self) -> CharxData:
        """Read the charger state once per cycle."""
        try:
            # Station info (name, firmware) never changes — read it once and
            # cache it to spare the charger's single-core CPU 5s polling.
            if self._global_data is None or not self._global_data.device_name:
                self._global_data = await self.client.read_global_data()
            connector_data = await self.client.read_connector_data()
        except ModbusException as err:
            raise UpdateFailed(f"Modbus communication error: {err}") from err
        except (ConnectionError, OSError) as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        # Track charging sessions (start/stop, RFID, energy, peak power)
        await self.session_tracker.update(connector_data)

        return CharxData(
            global_data=self._global_data,
            connector_data=connector_data,
        )
