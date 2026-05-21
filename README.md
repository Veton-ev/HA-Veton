# Veton EV Charger — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A local **Home Assistant** integration for **Veton EV chargers** built on the
Phoenix Contact **CHARX** controller. It talks to the charger directly over
**Modbus/TCP** on your own network — no cloud, no account, no internet
connection required.

It exposes the charger as a proper Home Assistant device with sensors,
controls, and a ready-made dashboard, so you can monitor and control charging
and build your own automations on top.

---

## Features

- 🔌 **Local & private** — direct Modbus/TCP to the charger, `local_polling`, polled every 5 s.
- 📊 **Rich sensors** — vehicle status (IEC 61851), charging power, session & total energy, per-phase voltage & current, charging/connection time, last RFID, release mode, error code, energy-meter type.
- 🎛️ **Controls** — enable/disable charging, set connector availability, and a max-charging-current slider (6–80 A).
- 🛡️ **Safety watchdog** — if Home Assistant stops talking to the charger, it falls back to the minimum current after 30 s instead of holding the last setpoint.
- 🧾 **Session log** — automatic charge-session tracking with RFID, energy and duration, plus a `veton.export_sessions_csv` service.
- 🖥️ **Auto dashboard** — a dedicated "Veton EV Charger" dashboard is added to your sidebar (it never overrides your existing default dashboard).

## Requirements

- A **Veton / Phoenix Contact CHARX** charger reachable on your LAN with its **Modbus/TCP server enabled** (default port `502`).
- **Home Assistant 2024.12** or newer.
- The charger's IP address (a static/reserved DHCP lease is recommended).

## Installation

### Option A — HACS (recommended)

1. In Home Assistant go to **HACS → ⋮ (top right) → Custom repositories**.
2. Add repository URL `https://github.com/Veton-ev/HA-Veton` and select category **Integration**, then **Add**.
3. Search for **Veton EV Charger** in HACS and click **Download**.
4. **Restart Home Assistant.**

### Option B — Manual

1. Copy the `custom_components/veton/` folder from this repo into your Home Assistant `config/custom_components/` directory (so you end up with `config/custom_components/veton/`).
2. **Restart Home Assistant.**

## Configuration

After restarting:

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Veton EV Charger**.
3. Enter:
   - **IP address** of the charger
   - **Modbus TCP port** (default `502`)
   - **Connector number** (default `1`; on multi-connector controllers the registers are offset by `connector × 1000`)
4. The integration tests the connection and creates the device, its entities, and the dashboard.

To change the connection later, open the integration and choose **Reconfigure**.

## Entities

| Type | Examples |
|------|----------|
| `sensor` | Vehicle status, charging power, session/total energy, voltage L1–L3, current L1–L3, charging/connection time, last RFID, release mode, error code, energy meter, total sessions |
| `switch` | Charging enabled, Available |
| `number` | Max charging current |

Some diagnostic sensors are disabled by default — enable them per entity if you want them.

## Smart charging (solar / dynamic tariff)

This integration is intentionally **device-only**: it exposes the charger and
its controls, and stops there. Solar-surplus, capacity limitation, and
dynamic-price charging are best done the Home Assistant way — by composing this
charger's entities with:

- a grid/energy meter integration of your choice (e.g. the official HomeWizard, P1, or your meter's own integration),
- an electricity-price integration (e.g. EnergyZero, Nord Pool, ENTSO-e),
- and Home Assistant **automations**, or a dedicated charge-optimiser integration.

Set the **Max charging current** number (or toggle **Charging enabled**) from
your automations to steer the charger.

## Services

`veton.export_sessions_csv` — returns all recorded charging sessions as CSV
(supports a response). Optional `entry_id` to target a specific charger.

## Troubleshooting

- **"Cannot connect"** — verify the IP, that port `502` is reachable from the HA host, and that the CHARX Modbus/TCP server is enabled.
- **No energy/metering values** — the charger needs a configured energy meter; check the *Energy meter* sensor.
- Enable debug logging by adding to `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.veton: debug
  ```

## License

[MIT](LICENSE) — free to use and modify.
