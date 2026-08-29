# veton-ha (HA-Veton) — Claude Code instructions

<!-- Template from veton-handbook/templates/CLAUDE.md.template. Keep every section; write
"none" rather than deleting one. Facts here must be checked against the code, not remembered.
Cross-cutting knowledge (fleet, runbooks, access, suppliers) lives in the handbook — link, don't copy. -->

## What this is
A standalone custom Home Assistant integration for Veton EV chargers (Phoenix Contact CHARX
controllers). It connects to the charger over **Modbus/TCP `:502`** and exposes it as an HA device:
sensors (status, power, energy, per-phase V/I, RFID, release mode, error code, meter type, session
count), switches (charge enable X300, availability X304), a number (max current X301), a session
tracker with CSV export, and a self-provisioned sidebar dashboard. **Device-only by design** —
smart charging (solar/tariff/capacity) is left to HA automations, as go-eCharger/Wallbox/evcc do.
Distributed **publicly via HACS as a custom repository (`Veton-ev/HA-Veton`)** — this repo is
read by customers and integrators. `haos-build/` is a separate concern: a turnkey Raspberry Pi HA
OS image with the integration pre-installed. Handbook: `veton-handbook/10-fleet/metering.md`
and `10-fleet/load-management.md` (register semantics), `00-orientation/seams.md` #2.

## Ownership
Owners: TBD (Brend / Andrii). Escalation: Jens. Handbook page: `veton-handbook/10-fleet/load-management.md`.

## Run / test / build
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt          # pytest, pytest-homeassistant-custom-component, pymodbus, voluptuous
python -m pytest -q                            # the command CI runs
gitleaks git --config .gitleaks.toml --exit-code 1 --log-opts=--all .
```
Tests (`tests/`): modbus decoders + register mapping + write offsets/clamping + reconnect,
session-tracker state machine + persistence, config/reconfigure/import flows, end-to-end
setup/unload, dashboard generation.

CI (every push/PR): `.github/workflows/ci.yml` job `ci` = gitleaks secret scan over the whole
history + `pip install -r requirements_test.txt` + `python -m pytest -q` on Python 3.13 (the
required check for branch protection). `.github/workflows/validate.yml` keeps hassfest + HACS
validation alongside it. Secret-scan pre-commit hook: `git config core.hooksPath .githooks` once
per clone. Agent fences (`.claude/settings.json` + `.claude/hooks/guard.sh`) block pushes to main
and force-pushes.

Live smoke test: run HA in Docker with `--network=host` to reach the CHARX
(`docker run -d --name ha --network=host -v /path/to/config:/config homeassistant/home-assistant:stable`),
copy `custom_components/veton/` into `/config/custom_components/veton/`, restart.

CI: `.github/workflows/ci.yml` (job id `ci`). A red `ci` blocks deploy.

## Deploy
There is no deploy pipeline: users install via HACS from a **tagged release on `main`**
(`manifest.json` `version`, currently 1.1.0; `hacs.json` minimum HA 2024.12.0); rollback = install
the previous release. Blast radius of a bad release: every customer/integrator HA install that
updates — a wrong register write (X301/X306/X307) reaches real chargers on other people's
sites, and there is no fleet channel to pull it back.

## Talks to (seams)
See handbook `00-orientation/seams.md`.
- **#2 Modbus register map** — `custom_components/veton/modbus_client.py` is one of the six
  copies, and one of the three **public** ones (with `Veton-EMS-Integration` and Veton-Loxone).
  Connector offset = `connector_number × 1000`; X300 enable, X301 setpoint, X304 availability,
  X306 watchdog timeout, X307 fallback current; registers 100–109 device name (ASCII), 110–113
  software version. Any register-semantics change discovered in `vetonlm`/`vetond` must be
  mirrored here because customers read this code.
- **The CHARX itself** (Modbus server `:502`; firmware-dependent — 1.9.x changes are in
  `traps.md` §5). No Veton cloud, no vetond, no MQTT.
- `haos-build/veton_setup/` (yaml-loaded `veton_setup:` helper) auto-discovers the CHARX on first
  boot and creates the config entry via `SOURCE_IMPORT` → `config_flow.async_step_import`.

## Where to look (`custom_components/veton/`)
| File | Purpose |
|---|---|
| `__init__.py` | entry: connects, sets the safety watchdog, starts the coordinator, registers the CSV service, provisions the sidebar dashboard |
| `config_flow.py` | UI setup (host/port/connector) + `reconfigure` + `import` steps; manual form is the only setup path (no scanning) |
| `coordinator.py` | `DataUpdateCoordinator`, polls every 5 s (global + connector data), runs the session tracker |
| `modbus_client.py` | async pymodbus client; 32-bit values MSW/LSW, registers big-endian |
| `sensor.py`, `switch.py`, `number.py` | entities (all `CoordinatorEntity[VetonCoordinator]`, `_attr_has_entity_name = True`, unique id `f"{entry.entry_id}_{key}"`) |
| `session_tracker.py` | sessions via status transitions, RFID, CSV export |
| `dashboard.py` | a *separate* sidebar Lovelace dashboard — never touches the user's Overview / `default_panel` |

## Gotchas (this repo only)
Cross-cutting traps: `veton-handbook/80-gotchas/traps.md` §3 (meters) and §4 (load management —
e.g. the write floor `max(6 A, cpMin)`, 4.8).

- **pymodbus ≥ 3.11 API**: `device_id=` (not `slave`), keyword-only `count=`:
  `client.read_holding_registers(address, count=count, device_id=1)`,
  `client.write_register(address, value, device_id=1)`. The manifest requirement is
  `pymodbus>=3.6.0` — keep the call shapes compatible with what HA actually pins.
- **The watchdog is set on connect** (X306 timeout, X307 fallback): if HA stops polling, the
  charger falls back to X307 — choose that value as the safe state, and never leave a charger with
  a watchdog armed and no writer.
- **Dashboard**: the URL path must contain a hyphen (`veton-charger`); persistence goes through
  HA's `DashboardsCollection` (never write storage files directly); do not set `default_panel`.
- **Config flow**: `async_step_reconfigure` needs HA ≥ 2024.12; `async_step_import` exists only
  for the turnkey-Pi helper.
- **`haos-build/veton_setup/` lives outside `custom_components/` on purpose**: HACS allows one
  integration per repo and the helper is image-only.
- Conventions: `from __future__ import annotations` everywhere; all I/O async; `_LOGGER =
  logging.getLogger(__name__)`; `loggers: ["pymodbus"]` in the manifest.
- **This repo is public.** No customer names, no fleet counts, no fault statistics, no internal
  hostnames or credentials — in code, tests, README or commit messages
  (`veton-handbook/80-gotchas/working-agreements.md`).

## Agent rules
- Work on a branch; open a PR; never push to `main` (enforced by `.claude/settings.json`
  + `.claude/hooks/guard.sh` and by branch protection).
- Never run deploy/ssh-to-production commands; the pipeline deploys from `main`.
- Never commit secrets; `gitleaks` pre-commit + CI will fail the commit/PR. Secrets live
  nowhere in this repo (a public integration needs none); the handbook `60-access/` says where,
  never the value.
- Write durable lessons to `veton-handbook/lessons/` (one file per lesson), not to
  personal memory.
- A release tag is a customer-facing deploy: run the full test suite and a live smoke test
  against a real CHARX before tagging, and never tag from an agent session.
