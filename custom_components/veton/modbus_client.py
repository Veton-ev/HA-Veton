"""Modbus TCP client for Phoenix Contact CHARX controller."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)


@dataclass
class CharxGlobalData:
    """Global station data (registers 0-999)."""

    device_name: str = ""
    software_version: str = ""
    num_controllers: int = 0
    total_power_mw: int = 0
    total_reactive_power_mvar: int = 0
    total_current_l1_ma: int = 0
    total_current_l2_ma: int = 0
    total_current_l3_ma: int = 0
    num_available: int = 0
    num_occupied: int = 0
    num_charging: int = 0
    num_error: int = 0


@dataclass
class CharxConnectorData:
    """Per-connector data (registers X000-X999)."""

    # Config
    charging_case: int = 0  # 0=socket, 1=connector
    max_current_setting: int = 0
    min_current_setting: int = 0
    energy_meter_type: int = 0
    release_mode: int = 0

    # Status - metering
    voltage_l1_mv: int = 0
    voltage_l2_mv: int = 0
    voltage_l3_mv: int = 0
    current_l1_ma: int = 0
    current_l2_ma: int = 0
    current_l3_ma: int = 0
    active_power_mw: int = 0
    reactive_power_mvar: int = 0
    apparent_power_mva: int = 0
    total_energy_wh: int = 0
    session_energy_wh: int = 0

    # Status - session
    evcc_id: str = ""
    rfid_uid: str = ""
    connection_time_s: int = 0
    charging_time_s: int = 0
    vehicle_status: str = ""
    current_pwm_pct: int = 0
    current_charge_a: int = 0
    connector_capacity_a: int = 0
    error_code: int = 0

    # Control (readable)
    charge_enabled: bool = False
    max_current_a: int = 0
    availability: bool = True
    watchdog_current_a: int = 0
    watchdog_timer_s: int = 0


def _decode_ascii(registers: list[int]) -> str:
    """Decode Modbus registers to ASCII string."""
    raw = b""
    for reg in registers:
        raw += struct.pack(">H", reg)
    return raw.decode("ascii", errors="replace").rstrip("\x00").strip()


def _decode_int32(registers: list[int]) -> int:
    """Decode 2 registers as signed 32-bit int (MSW first)."""
    return struct.unpack(">i", struct.pack(">HH", *registers))[0]


def _decode_uint32(registers: list[int]) -> int:
    """Decode 2 registers as unsigned 32-bit int (MSW first)."""
    return struct.unpack(">I", struct.pack(">HH", *registers))[0]


def _decode_int64(registers: list[int]) -> int:
    """Decode 4 registers as signed 64-bit int."""
    return struct.unpack(">q", struct.pack(">HHHH", *registers))[0]


class CharxModbusClient:
    """Async Modbus TCP client for CHARX controller."""

    def __init__(self, host: str, port: int, slave: int, connector: int) -> None:
        self._host = host
        self._port = port
        self._slave = slave
        self._connector = connector
        self._client: AsyncModbusTcpClient | None = None

    @property
    def _base(self) -> int:
        """Base register offset for the connector."""
        return self._connector * 1000

    async def connect(self) -> bool:
        """Connect to the CHARX controller."""
        self._client = AsyncModbusTcpClient(self._host, port=self._port)
        return await self._client.connect()

    async def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()

    async def _read_holding(self, address: int, count: int) -> list[int]:
        """Read holding registers."""
        if not self._client:
            raise ModbusException("Not connected")
        result = await self._client.read_holding_registers(
            address, count=count, device_id=self._slave
        )
        if result.isError():
            raise ModbusException(f"Error reading register {address}: {result}")
        return list(result.registers)

    async def _write_holding(self, address: int, value: int) -> None:
        """Write a single holding register."""
        if not self._client:
            raise ModbusException("Not connected")
        result = await self._client.write_register(
            address, value, device_id=self._slave
        )
        if result.isError():
            raise ModbusException(f"Error writing register {address}: {result}")

    async def read_global_data(self) -> CharxGlobalData:
        """Read global station data."""
        data = CharxGlobalData()

        try:
            regs = await self._read_holding(100, 15)
            data.device_name = _decode_ascii(regs[0:10])
            data.software_version = _decode_ascii(regs[10:14])
            data.num_controllers = regs[14]
        except ModbusException as err:
            _LOGGER.warning("Failed to read station info: %s", err)

        try:
            regs = await self._read_holding(147, 7)
            data.num_error = regs[1]  # 148
            data.num_available = regs[2]  # 149
            data.num_occupied = regs[3]  # 150
            data.num_charging = regs[4]  # 151
            data.total_power_mw = _decode_int32(regs[5:7])  # 152-153
        except ModbusException as err:
            _LOGGER.warning("Failed to read station status: %s", err)

        try:
            regs = await self._read_holding(158, 6)
            data.total_current_l1_ma = _decode_int32(regs[0:2])
            data.total_current_l2_ma = _decode_int32(regs[2:4])
            data.total_current_l3_ma = _decode_int32(regs[4:6])
        except ModbusException as err:
            _LOGGER.warning("Failed to read station currents: %s", err)

        return data

    async def read_connector_data(self) -> CharxConnectorData:
        """Read per-connector data."""
        data = CharxConnectorData()
        base = self._base

        # Config registers X100-X121
        try:
            regs = await self._read_holding(base + 100, 21)
            data.charging_case = regs[0]
            data.max_current_setting = regs[1]
            data.min_current_setting = regs[2]
            data.energy_meter_type = regs[12]  # X112
            data.release_mode = regs[20]  # X120
        except ModbusException as err:
            _LOGGER.warning("Failed to read connector config: %s", err)

        # Status registers X232-X299
        try:
            # Voltages and currents: X232-X243 (12 registers)
            regs = await self._read_holding(base + 232, 12)
            data.voltage_l1_mv = _decode_int32(regs[0:2])
            data.voltage_l2_mv = _decode_int32(regs[2:4])
            data.voltage_l3_mv = _decode_int32(regs[4:6])
            data.current_l1_ma = _decode_int32(regs[6:8])
            data.current_l2_ma = _decode_int32(regs[8:10])
            data.current_l3_ma = _decode_int32(regs[10:12])
        except ModbusException as err:
            _LOGGER.warning("Failed to read voltages/currents: %s", err)

        try:
            # Power and energy: X244-X261 (18 registers)
            regs = await self._read_holding(base + 244, 18)
            data.active_power_mw = _decode_int32(regs[0:2])
            data.reactive_power_mvar = _decode_int32(regs[2:4])
            data.apparent_power_mva = _decode_int32(regs[4:6])
            data.total_energy_wh = _decode_int64(regs[6:10])
        except ModbusException as err:
            _LOGGER.warning("Failed to read power/energy: %s", err)

        try:
            # EVCC ID (X265, 10 regs) + RFID (X275, 10 regs) + times + session energy
            regs = await self._read_holding(base + 265, 28)
            data.evcc_id = _decode_ascii(regs[0:10])
            data.rfid_uid = _decode_ascii(regs[10:20])
            data.connection_time_s = _decode_uint32(regs[20:22])
            data.charging_time_s = _decode_uint32(regs[22:24])
            data.session_energy_wh = _decode_int64(regs[24:28])
        except ModbusException as err:
            _LOGGER.warning("Failed to read session data: %s", err)

        try:
            # Error code + misc status: X293-X299
            regs = await self._read_holding(base + 293, 7)
            data.error_code = _decode_uint32(regs[0:2])
            data.current_pwm_pct = regs[3]  # X296
            data.current_charge_a = regs[4]  # X297
            data.connector_capacity_a = regs[5]  # X298
        except ModbusException as err:
            _LOGGER.warning("Failed to read status: %s", err)

        try:
            # Vehicle status: X299 (1 register, ASCII-encoded)
            regs = await self._read_holding(base + 299, 1)
            data.vehicle_status = _decode_ascii(regs)
        except ModbusException as err:
            _LOGGER.warning("Failed to read vehicle status: %s", err)

        # Control registers X300-X307
        try:
            regs = await self._read_holding(base + 300, 8)
            data.charge_enabled = regs[0] == 1
            data.max_current_a = regs[1]
            data.availability = regs[4] == 1  # X304
            data.watchdog_current_a = regs[6]  # X306
            data.watchdog_timer_s = regs[7]  # X307
        except ModbusException as err:
            _LOGGER.warning("Failed to read control registers: %s", err)

        return data

    # --- Write commands ---

    async def set_charge_enabled(self, enabled: bool) -> None:
        """Enable or disable charging (X300)."""
        await self._write_holding(self._base + 300, 1 if enabled else 0)

    async def set_max_current(self, current_a: int) -> None:
        """Set maximum charging current in amps (X301, range 6-80)."""
        current_a = max(6, min(80, current_a))
        await self._write_holding(self._base + 301, current_a)

    async def set_availability(self, available: bool) -> None:
        """Set connector availability (X304)."""
        await self._write_holding(self._base + 304, 1 if available else 0)

    async def set_watchdog(self, fallback_current_a: int, timeout_s: int) -> None:
        """Configure watchdog: fallback current (X306) and timer (X307)."""
        fallback_current_a = max(6, min(80, fallback_current_a))
        await self._write_holding(self._base + 306, fallback_current_a)
        await self._write_holding(self._base + 307, timeout_s)

    async def refresh_watchdog(self, timeout_s: int) -> None:
        """Reset the watchdog timer (X307)."""
        await self._write_holding(self._base + 307, timeout_s)

    async def set_global_max_current(self, current_a: int) -> None:
        """Set dynamic max target current for load management (register 167)."""
        await self._write_holding(167, current_a)

    async def set_global_availability(self, available: bool) -> None:
        """Set global availability for all controllers (register 164)."""
        await self._write_holding(164, 1 if available else 0)
