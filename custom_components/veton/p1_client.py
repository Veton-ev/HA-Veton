"""HomeWizard P1 meter local API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiohttp

_LOGGER = logging.getLogger(__name__)

P1_API_TIMEOUT = 10


@dataclass
class P1Data:
    """Data from the HomeWizard P1 meter."""

    # Grid power (positive = import, negative = export)
    active_power_w: float = 0.0
    active_power_l1_w: float = 0.0
    active_power_l2_w: float = 0.0
    active_power_l3_w: float = 0.0

    # Voltage per phase
    active_voltage_l1_v: float = 0.0
    active_voltage_l2_v: float = 0.0
    active_voltage_l3_v: float = 0.0

    # Current per phase
    active_current_l1_a: float = 0.0
    active_current_l2_a: float = 0.0
    active_current_l3_a: float = 0.0

    # Energy totals
    total_power_import_kwh: float = 0.0
    total_power_import_t1_kwh: float = 0.0
    total_power_import_t2_kwh: float = 0.0
    total_power_export_kwh: float = 0.0
    total_power_export_t1_kwh: float = 0.0
    total_power_export_t2_kwh: float = 0.0

    # Gas
    total_gas_m3: float | None = None

    # Frequency
    active_frequency_hz: float = 0.0

    # Peak demand (Belgian capacity tariff)
    active_power_average_w: float | None = None
    monthly_power_peak_w: float | None = None

    # Device info
    meter_model: str = ""
    smr_version: int = 0
    wifi_strength: int = 0


@dataclass
class P1DeviceInfo:
    """Device identification from the P1 meter."""

    product_name: str = ""
    product_type: str = ""
    serial: str = ""
    firmware_version: str = ""
    api_version: str = ""


class P1Client:
    """Async HTTP client for the HomeWizard P1 meter local API."""

    def __init__(self, host: str) -> None:
        self._host = host
        self._base_url = f"http://{host}"
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=P1_API_TIMEOUT)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_device_info(self) -> P1DeviceInfo:
        """GET /api — returns basic device identification."""
        session = await self._ensure_session()
        async with session.get(f"{self._base_url}/api") as resp:
            resp.raise_for_status()
            data = await resp.json()
        return P1DeviceInfo(
            product_name=data.get("product_name", ""),
            product_type=data.get("product_type", ""),
            serial=data.get("serial", ""),
            firmware_version=data.get("firmware_version", ""),
            api_version=data.get("api_version", ""),
        )

    async def get_data(self) -> P1Data:
        """GET /api/v1/data — returns current measurement data."""
        session = await self._ensure_session()
        async with session.get(f"{self._base_url}/api/v1/data") as resp:
            resp.raise_for_status()
            raw = await resp.json()

        return P1Data(
            active_power_w=raw.get("active_power_w", 0.0),
            active_power_l1_w=raw.get("active_power_l1_w", 0.0),
            active_power_l2_w=raw.get("active_power_l2_w", 0.0),
            active_power_l3_w=raw.get("active_power_l3_w", 0.0),
            active_voltage_l1_v=raw.get("active_voltage_l1_v", 0.0),
            active_voltage_l2_v=raw.get("active_voltage_l2_v", 0.0),
            active_voltage_l3_v=raw.get("active_voltage_l3_v", 0.0),
            active_current_l1_a=raw.get("active_current_l1_a", 0.0),
            active_current_l2_a=raw.get("active_current_l2_a", 0.0),
            active_current_l3_a=raw.get("active_current_l3_a", 0.0),
            total_power_import_kwh=raw.get("total_power_import_kwh", 0.0),
            total_power_import_t1_kwh=raw.get("total_power_import_t1_kwh", 0.0),
            total_power_import_t2_kwh=raw.get("total_power_import_t2_kwh", 0.0),
            total_power_export_kwh=raw.get("total_power_export_kwh", 0.0),
            total_power_export_t1_kwh=raw.get("total_power_export_t1_kwh", 0.0),
            total_power_export_t2_kwh=raw.get("total_power_export_t2_kwh", 0.0),
            total_gas_m3=raw.get("total_gas_m3"),
            active_frequency_hz=raw.get("active_frequency_hz", 0.0),
            active_power_average_w=raw.get("active_power_average_w"),
            monthly_power_peak_w=raw.get("montly_power_peak_w"),  # typo in HW API
            meter_model=raw.get("meter_model", ""),
            smr_version=raw.get("smr_version", 0),
            wifi_strength=raw.get("wifi_strength", 0),
        )

    async def test_connection(self) -> bool:
        """Test if the P1 meter is reachable and API is enabled."""
        try:
            await self.get_device_info()
            return True
        except Exception:
            return False
