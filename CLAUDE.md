# Veton EV Charger — Home Assistant Integration

## Project Overview

Custom Home Assistant integration for **Veton EV chargers** with Phoenix Contact CHARX controllers. Connects via Modbus/TCP, integrates HomeWizard P1 meters for grid monitoring, and uses EnergyZero day-ahead electricity prices for smart charging.

Designed for turnkey Raspberry Pi deployment: flash → boot → auto-discovers charger + P1 → dashboard appears.

## Architecture

```
VetonCoordinator (polls every 5s)
├── CharxModbusClient ──► CHARX controller (Modbus/TCP port 502)
├── P1Client           ──► HomeWizard P1 meter (HTTP local API)
├── TariffClient       ──► EnergyZero public API (HTTPS, no auth)
└── EmsController      ──► Computes target current, writes back to CHARX
```

**Two integrations:**
- `custom_components/veton/` — Main integration (config_flow, entities, EMS, dashboard)
- `custom_components/veton_setup/` — Lightweight yaml-loaded helper that auto-discovers and creates config entry via `SOURCE_IMPORT` on first boot

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Entry point: creates clients, coordinator, EMS; registers services; auto-creates dashboard |
| `modbus_client.py` | Async pymodbus client for CHARX registers. Connector offset = `connector_number * 1000` |
| `p1_client.py` | Aiohttp client for HomeWizard P1 local API (`/api/v1/data`) |
| `tariff_client.py` | EnergyZero API client with date-based caching |
| `ems.py` | Energy Management System: 7 modes (solar, capacity, tariff), hysteresis, EMA smoothing |
| `coordinator.py` | `DataUpdateCoordinator` — polls all sources, runs EMS, writes charger |
| `sensor.py` | 40+ sensors: charger metrics, P1 grid data, EMS diagnostics, tariff prices |
| `switch.py` | 2 switches: charge enable (register X300), availability (X304) |
| `number.py` | 6 number entities: max current (X301), EMS tuning parameters |
| `select.py` | 1 select: EMS mode picker |
| `config_flow.py` | Multi-step wizard + `async_step_import` for zero-touch setup |
| `dashboard.py` | Auto-provisions Lovelace dashboard via HA's internal APIs (DashboardsCollection, LovelaceStorage) |
| `session_tracker.py` | Detects charge sessions via status transitions, logs RFID, CSV export |
| `first_boot.py` | EVENT_HOMEASSISTANT_STARTED listener to trigger config flow |
| `veton_setup/__init__.py` | Auto-discovery: hostname resolution → subnet scan → SOURCE_IMPORT |

## Technical Notes

### Modbus (pymodbus 3.11+)
- API uses `device_id` (not `slave`), keyword-only `count`:
  ```python
  client.read_holding_registers(address, count=count, device_id=1)
  client.write_register(address, value, device_id=1)
  ```
- 32-bit values: MSW/LSW byte order, registers are big-endian
- Register 100-109: device name (ASCII, 10 registers)
- Watchdog: register X306 (timeout), X307 (fallback current)

### HomeWizard P1
- Local API: `http://<ip>/api` (device info), `http://<ip>/api/v1/data` (readings)
- mDNS: `_hwenergy._tcp`
- Product detection: `product_type` contains "HWE-P1" or "energy"

### EnergyZero API
- Endpoint: `https://public.api.energyzero.nl/public/v1/prices`
- Response: prices in `base`/`all_in_with_vat` arrays, each entry `{start, end, price: {value}}`
- No auth required, free, covers NL/BE

### Dashboard
- URL path must contain a hyphen (HA requirement): `veton-charger`
- Uses `DashboardsCollection` (HA's own Store) for persistence — never write storage files directly
- Uses `frontend.async_system_store` to set `default_panel`
- `LovelaceStorage.async_save()` fires `EVENT_LOVELACE_UPDATED` (frontend reloads)

### Auto-Setup Flow
1. `veton_setup` loaded via `veton_setup:` in configuration.yaml (no config_flow)
2. On `EVENT_HOMEASSISTANT_STARTED`: discovers CHARX (hostname first, subnet scan fallback)
3. Discovers P1 on same subnet via HTTP probe
4. Creates config entry via `flow.async_init(domain, context={"source": SOURCE_IMPORT}, data={...})`
5. `async_step_import` in config_flow creates entry — no UI interaction needed
6. `async_setup_entry` connects, starts coordinator, creates dashboard

### Why `veton_setup` Exists Separately
HA ignores `async_setup()` for integrations with `config_flow: true` in manifest. The helper integration has no config_flow, so its `async_setup()` is called from yaml config.

## Conventions

- `from __future__ import annotations` in every file
- All I/O is async (`await`)
- Logging: `_LOGGER = logging.getLogger(__name__)`
- Entity unique IDs: `f"{entry.entry_id}_{key}"`
- All entities inherit `CoordinatorEntity[VetonCoordinator]`
- `_attr_has_entity_name = True` — entity name appended to device name
- Error handling: Modbus errors → `UpdateFailed`; P1/tariff errors → log + continue with None

## Dependencies

- `pymodbus >= 3.6.0`
- `aiohttp >= 3.9.0`
- Home Assistant `>= 2024.1.0`

## Testing

Run HA in Docker with `--network=host` to reach CHARX on the local network:
```bash
docker run -d --name ha --network=host -v /path/to/config:/config homeassistant/home-assistant:stable
```

Deploy integration files to `/path/to/config/custom_components/veton/` and `veton_setup/`.
Add `veton_setup:` to `configuration.yaml` for auto-discovery.

No formal test suite yet. Integration tested manually against real CHARX (192.168.0.108) and HomeWizard P1 (192.168.0.195).

## Common Pitfalls

- Dashboard URL path **must** contain a hyphen (`veton-charger`, not `veton`)
- Don't write `.storage/` files directly — HA's Store objects overwrite manual edits
- `DashboardsCollection` is a local variable in lovelace `async_setup` — create a new instance sharing the same storage file
- pymodbus 3.11 renamed `slave` → `device_id` and made `count` keyword-only
- EnergyZero changed response format: prices are in nested `{price: {value}}` objects
