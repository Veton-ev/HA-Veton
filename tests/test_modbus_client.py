"""Tests for the CHARX Modbus client: decoding, register mapping, writes, reconnect."""

from __future__ import annotations

import pytest

from custom_components.veton.modbus_client import (
    CharxModbusClient,
    _decode_ascii,
    _decode_int32,
    _decode_int64,
    _decode_uint32,
)


# ── Pure decoders ───────────────────────────────────────────────────


def test_decode_ascii_strips_nulls_and_whitespace():
    # 'CH','AR','X\x00' -> "CHARX"
    assert _decode_ascii([0x4348, 0x4152, 0x5800]) == "CHARX"
    assert _decode_ascii([0x0000]) == ""


def test_decode_int32_signed():
    assert _decode_int32([0x0000, 0x0001]) == 1
    assert _decode_int32([0x0001, 0x0000]) == 65536
    assert _decode_int32([0xFFFF, 0xFFFF]) == -1  # signed


def test_decode_uint32_unsigned():
    assert _decode_uint32([0xFFFF, 0xFFFF]) == 4294967295
    assert _decode_uint32([0x0001, 0x0000]) == 65536


def test_decode_int64():
    assert _decode_int64([0x0000, 0x0000, 0x0000, 0x000A]) == 10
    assert _decode_int64([0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF]) == -1


# ── Register mapping (read_connector_data) ──────────────────────────


@pytest.fixture
def canned_client():
    """A client whose _read_holding returns canned register blocks.

    Connector 1 => base offset 1000.
    """
    client = CharxModbusClient("10.0.0.5", 502, 1, 1)

    blocks: dict[int, list[int]] = {
        # X100..X120 (count 21): charging_case, max_setting, min_setting,
        # ... idx12 = meter type, idx20 = release mode
        1100: [1, 16, 6] + [0] * 9 + [11] + [0] * 7 + [4],
        # X232..X243 (count 12): V L1/L2/L3, I L1/L2/L3 as int32 MSW/LSW pairs.
        # 230000 = 0x00038270 -> (0x0003, 0x8270); 10000 = (0x0000, 0x2710)
        1232: [0x0003, 0x8270, 0x0003, 0x8658, 0x0003, 0x7E88,
               0x0000, 0x2710, 0, 0, 0, 0],
        # X244..X261 (count 18): P, Q, S (int32) + total energy (int64)
        1244: [0, 7000, 0, 0, 0, 0, 0, 0, 0, 1234] + [0] * 8,
        # X265..X292 (count 28): evcc(10) + rfid(10) + conn_time + chg_time + session_energy(int64)
        1265: ([0] * 10) + [0x4142, 0x4344] + [0] * 8 + [0, 120, 0, 60, 0, 0, 0, 500],
        # X293..X299 (count 7): error(int32) + pwm + charge_a + capacity
        1293: [0, 0, 0, 30, 12, 32, 0],
        # X299 (count 1): vehicle status "C2" = 0x4332
        1299: [0x4332],
        # X300..X307 (count 8): enabled, max_a, _, _, avail, _, wd_current, wd_timer
        1300: [1, 16, 0, 0, 1, 0, 6, 30],
    }

    async def fake_read(address: int, count: int) -> list[int]:
        regs = blocks.get(address, [0] * count)
        assert len(regs) == count, f"block {address} expected {count}, got {len(regs)}"
        return regs

    client._read_holding = fake_read  # type: ignore[assignment]
    return client


async def test_read_connector_data_maps_registers(canned_client):
    data = await canned_client.read_connector_data()

    assert data.charging_case == 1
    assert data.max_current_setting == 16
    assert data.min_current_setting == 6
    assert data.energy_meter_type == 11
    assert data.release_mode == 4

    assert data.voltage_l1_mv == 230000
    assert data.current_l1_ma == 10000
    assert data.active_power_mw == 7000
    assert data.total_energy_wh == 1234
    assert data.session_energy_wh == 500
    assert data.rfid_uid == "ABCD"
    assert data.connection_time_s == 120
    assert data.charging_time_s == 60

    assert data.current_charge_a == 12
    assert data.connector_capacity_a == 32
    assert data.vehicle_status == "C2"

    assert data.charge_enabled is True
    assert data.max_current_a == 16
    assert data.availability is True
    assert data.watchdog_current_a == 6
    assert data.watchdog_timer_s == 30


async def test_read_global_data_maps_name_and_version():
    client = CharxModbusClient("10.0.0.5", 502, 1, 1)

    async def fake_read(address: int, count: int) -> list[int]:
        if address == 100:  # name(10) + version(4) + num_controllers
            return [0x4348, 0x4152, 0x5800] + [0] * 7 + [0x312E, 0x3900, 0, 0] + [3]
        return [0] * count

    client._read_holding = fake_read  # type: ignore[assignment]
    data = await client.read_global_data()
    assert data.device_name == "CHARX"
    assert data.software_version == "1.9"
    assert data.num_controllers == 3


# ── Writes: connector offset + clamping ─────────────────────────────


@pytest.fixture
def write_recorder():
    """A connector-2 client (base 2000) recording every write."""
    client = CharxModbusClient("10.0.0.5", 502, 1, 2)
    writes: list[tuple[int, int]] = []

    async def fake_write(address: int, value: int) -> None:
        writes.append((address, value))

    client._write_holding = fake_write  # type: ignore[assignment]
    return client, writes


async def test_set_max_current_clamps_and_offsets(write_recorder):
    client, writes = write_recorder
    await client.set_max_current(100)  # clamp to 80
    await client.set_max_current(2)    # clamp to 6
    assert writes == [(2301, 80), (2301, 6)]


async def test_charge_enable_and_availability_addresses(write_recorder):
    client, writes = write_recorder
    await client.set_charge_enabled(True)
    await client.set_availability(False)
    assert writes == [(2300, 1), (2304, 0)]


async def test_watchdog_writes(write_recorder):
    client, writes = write_recorder
    await client.set_watchdog(fallback_current_a=3, timeout_s=30)  # clamp 3 -> 6
    await client.refresh_watchdog(45)
    assert writes == [(2306, 6), (2307, 30), (2307, 45)]


# ── Reconnect behaviour ─────────────────────────────────────────────


class _FakeResult:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class _FakePyModbus:
    """Stand-in for AsyncModbusTcpClient that starts disconnected."""

    def __init__(self):
        self.connected = False
        self.connect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self.connected = True
        return True

    def close(self):
        self.connected = False

    async def read_holding_registers(self, address, count, device_id):
        return _FakeResult([7] * count)


async def test_read_reconnects_when_socket_dropped():
    client = CharxModbusClient("10.0.0.5", 502, 1, 1)
    fake = _FakePyModbus()
    client._client = fake  # injected, starts disconnected

    regs = await client._read_holding(1000, 2)

    assert fake.connect_calls == 1  # reconnected transparently
    assert regs == [7, 7]

    # Already connected -> no further reconnect
    await client._read_holding(1000, 2)
    assert fake.connect_calls == 1
