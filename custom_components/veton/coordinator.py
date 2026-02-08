"""Data update coordinator for Veton EV Charger."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.exceptions import ModbusException

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .ems import EmsController
from .modbus_client import CharxConnectorData, CharxGlobalData, CharxModbusClient
from .p1_client import P1Client, P1Data
from .session_tracker import SessionTracker
from .tariff_client import TariffClient, TariffData

_LOGGER = logging.getLogger(__name__)

# Tariff data is fetched less frequently (every 15 min, or on cache miss)
TARIFF_REFRESH_INTERVAL = 900  # seconds


@dataclass
class CharxData:
    """Combined data from the CHARX controller and optional P1 meter."""

    global_data: CharxGlobalData
    connector_data: CharxConnectorData
    p1_data: P1Data | None = None
    tariff_data: TariffData | None = None


class VetonCoordinator(DataUpdateCoordinator[CharxData]):
    """Coordinator that polls CHARX + P1 + tariffs and runs the EMS."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: CharxModbusClient,
        session_tracker: SessionTracker,
        p1_client: P1Client | None = None,
        ems: EmsController | None = None,
        tariff_client: TariffClient | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.p1_client = p1_client
        self.session_tracker = session_tracker
        self.ems = ems
        self.tariff_client = tariff_client
        self._tariff_data: TariffData | None = None
        self._tariff_poll_counter = 0

    @property
    def has_p1(self) -> bool:
        return self.p1_client is not None

    @property
    def has_tariffs(self) -> bool:
        return self.tariff_client is not None

    async def _async_update_data(self) -> CharxData:
        """Fetch data, run EMS, apply control output."""
        # ── 1. Read CHARX ────────────────────────────────────────
        try:
            global_data = await self.client.read_global_data()
            connector_data = await self.client.read_connector_data()
        except ModbusException as err:
            raise UpdateFailed(f"Modbus communication error: {err}") from err
        except (ConnectionError, OSError) as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        # Track charging sessions
        self.session_tracker.update(connector_data)

        # ── 2. Read P1 meter ─────────────────────────────────────
        p1_data = None
        if self.p1_client:
            try:
                p1_data = await self.p1_client.get_data()
            except Exception as err:
                _LOGGER.warning("P1 meter read failed: %s", err)

        # ── 3. Refresh tariff data (every ~15 min) ───────────────
        if self.tariff_client:
            self._tariff_poll_counter += 1
            # Fetch every TARIFF_REFRESH_INTERVAL / DEFAULT_SCAN_INTERVAL cycles
            cycles = TARIFF_REFRESH_INTERVAL // DEFAULT_SCAN_INTERVAL
            if self._tariff_data is None or self._tariff_poll_counter >= cycles:
                self._tariff_poll_counter = 0
                try:
                    self._tariff_data = await self.tariff_client.fetch_prices()
                except Exception as err:
                    _LOGGER.warning("Tariff fetch failed: %s", err)

            # Pass tariff data to EMS
            if self.ems and self._tariff_data:
                self.ems.tariff_data = self._tariff_data

        # ── 4. Run EMS control loop ──────────────────────────────
        if self.ems and p1_data:
            vehicle_connected = connector_data.vehicle_status in (
                "B1", "B2", "C1", "C2",
            )
            charger_power_w = connector_data.active_power_mw / 1000

            result = self.ems.compute(
                grid_power_w=p1_data.active_power_w,
                grid_current_l1_a=p1_data.active_current_l1_a,
                grid_current_l2_a=p1_data.active_current_l2_a,
                grid_current_l3_a=p1_data.active_current_l3_a,
                charger_power_w=charger_power_w,
                charger_current_a=connector_data.current_charge_a,
                vehicle_connected=vehicle_connected,
                charger_max_configured_a=connector_data.max_current_setting,
            )

            # ── 5. Apply EMS output to charger ───────────────────
            try:
                if result.should_charge:
                    if not connector_data.charge_enabled:
                        await self.client.set_charge_enabled(True)
                    if result.target_current_a != connector_data.max_current_a:
                        await self.client.set_max_current(result.target_current_a)
                else:
                    if connector_data.charge_enabled:
                        await self.client.set_charge_enabled(False)
            except Exception as err:
                _LOGGER.warning("EMS control write failed: %s", err)

        return CharxData(
            global_data=global_data,
            connector_data=connector_data,
            p1_data=p1_data,
            tariff_data=self._tariff_data,
        )
