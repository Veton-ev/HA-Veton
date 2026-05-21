# Veton EV Charger — Home Assistant Integration

## Project Overview

Standalone custom Home Assistant integration for **Veton EV chargers** with
Phoenix Contact CHARX controllers. Connects to the charger over **Modbus/TCP**
and exposes it as a Home Assistant device (sensors + controls + auto dashboard).

It is **device-only by design**: it controls and monitors the charger and
nothing else. Smart charging (solar/tariff/capacity) is left to Home Assistant
automations + other integrations (grid meter, price provider) — see README.
This mirrors how mature charger integrations (go-eCharger, Wallbox, evcc) work.

Distributed publicly via **HACS as a custom repository** (`Veton-ev/HA-Veton`).

## Architecture

```
VetonCoordinator (polls every 5s)
└── CharxModbusClient ──► CHARX controller (Modbus/TCP port 502)
        │
        └── SessionTracker (detects charge sessions, RFID, CSV export)
```

Single integration: `custom_components/veton/`.

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Entry point: connects, sets safety watchdog, starts coordinator, registers CSV service, provisions the sidebar dashboard |
| `config_flow.py` | UI setup (host/port/connector) + `reconfigure` step + `import` step (used by the optional turnkey-Pi helper) |
| `coordinator.py` | `DataUpdateCoordinator` — reads CHARX global + connector data, runs the session tracker |
| `modbus_client.py` | Async pymodbus client for CHARX registers. Connector offset = `connector_number * 1000` |
| `sensor.py` | Charger sensors: status, power, energy, per-phase V/I, times, RFID, release mode, error code, meter type, session count |
| `switch.py` | Charge enable (X300), availability (X304) |
| `number.py` | Max charging current (X301) |
| `session_tracker.py` | Detects sessions via status transitions, logs RFID, CSV export |
| `dashboard.py` | Provisions a *separate* sidebar Lovelace dashboard — never touches the user's default Overview / default_panel |

## Technical Notes

### Modbus (pymodbus 3.11+)
- API uses `device_id` (not `slave`), keyword-only `count`:
  ```python
  client.read_holding_registers(address, count=count, device_id=1)
  client.write_register(address, value, device_id=1)
  ```
- 32-bit values: MSW/LSW byte order, registers are big-endian
- Register 100-109: device name (ASCII); 110-113: software version
- Watchdog: register X306 (timeout), X307 (fallback current)

### Dashboard
- URL path must contain a hyphen (HA requirement): `veton-charger`
- Uses `DashboardsCollection` (HA's own Store) for persistence — never write storage files directly
- **Does not** set `default_panel` or overwrite the default Overview — it only adds a sidebar dashboard

### Config flow
- Manual connection form is the only setup path (no network scanning)
- `async_step_reconfigure` lets the user change host/port/connector after setup (needs HA ≥ 2024.12)
- `async_step_import` exists for the turnkey-Pi helper (`haos-build/veton_setup/`)

## Conventions

- `from __future__ import annotations` in every file
- All I/O is async (`await`)
- Logging: `_LOGGER = logging.getLogger(__name__)`
- Entity unique IDs: `f"{entry.entry_id}_{key}"`
- All entities inherit `CoordinatorEntity[VetonCoordinator]`
- `_attr_has_entity_name = True`

## Dependencies

- `pymodbus >= 3.6.0`
- Home Assistant `>= 2024.12.0`

## Turnkey Raspberry Pi image (separate concern)

`haos-build/` builds a custom HA OS image with this integration pre-installed.
`haos-build/veton_setup/` is a yaml-loaded helper (`veton_setup:`) that
auto-discovers the CHARX on first boot and creates the config entry via
`SOURCE_IMPORT`. It lives **outside** `custom_components/` on purpose: HACS
allows only one integration per repo, and the helper is image-only — it is not
part of the standalone HACS integration.

## Testing

Unit tests (pytest + `pytest-homeassistant-custom-component`) live in `tests/`:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```
Coverage: modbus decoders + register mapping + write offsets/clamping +
reconnect, session-tracker state machine + persistence, config/reconfigure/
import flows, end-to-end setup/unload, dashboard generation. CI runs hassfest +
HACS validation + pytest (`.github/workflows/validate.yml`).

For a live smoke test, run HA in Docker with `--network=host` to reach the CHARX:
```bash
docker run -d --name ha --network=host -v /path/to/config:/config homeassistant/home-assistant:stable
```
Deploy to `/config/custom_components/veton/` and restart.
