"""Config flow for Veton EV Charger — branded multi-step setup wizard."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from pymodbus.client import AsyncModbusTcpClient

from .const import (
    CONF_CONNECTOR,
    CONF_P1_ENABLED,
    CONF_P1_HOST,
    DEFAULT_CONNECTOR,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    DOMAIN,
)
from .modbus_client import CharxModbusClient
from .p1_client import P1Client

_LOGGER = logging.getLogger(__name__)

# Known CHARX hostnames to try resolving before subnet scan
_CHARX_HOSTNAMES = ["ev3000", "charx", "charx-sec"]

# Common subnets to scan for CHARX controllers
_COMMON_SUBNETS = ["192.168.0", "192.168.1", "192.168.2", "10.0.0", "10.0.1"]


class VetonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Branded multi-step setup wizard for Veton EV Charger."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._charx_host: str = ""
        self._charx_port: int = DEFAULT_PORT
        self._charx_connector: int = DEFAULT_CONNECTOR
        self._charx_device_name: str = ""
        self._p1_host: str = ""
        self._p1_discovered: dict[str, str] = {}  # serial -> ip
        self._charx_discovered: dict[str, str] = {}  # ip -> device_name

    # ── Import: fully automatic setup from veton_setup helper ──────

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle automatic import from veton_setup (no UI needed)."""
        host = import_data["host"]
        port = import_data.get("port", DEFAULT_PORT)
        connector = import_data.get("connector", DEFAULT_CONNECTOR)

        unique_id = f"{host}:{port}:{connector}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        device_name = import_data.get("device_name", f"CHARX ({host})")
        title = f"Veton Charger - {device_name}"
        if import_data.get("p1_enabled"):
            title += " + P1"

        return self.async_create_entry(
            title=title,
            data={
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_CONNECTOR: connector,
                CONF_P1_ENABLED: import_data.get("p1_enabled", False),
                CONF_P1_HOST: import_data.get("p1_host", ""),
            },
        )

    # ── Auto-discovery: triggered on first boot ─────────────────────

    async def async_step_onboarding(
        self, data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle auto-discovery during onboarding (fresh install)."""
        return await self.async_step_user()

    # ── Step 1: Welcome ──────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Welcome screen — press Next to scan for chargers."""
        if user_input is not None:
            # User clicked Next — scan for chargers, then show step 2
            await self._discover_charx()
            return await self.async_step_charger()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "brand": "Veton",
                "website": "veton.be",
            },
        )

    # ── Step 2: Charger connection ───────────────────────────────────

    async def async_step_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Select or enter the CHARX controller."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Determine host from dropdown or manual input
            host = user_input.get("discovered_charger", "")
            if not host or host == "manual":
                host = user_input.get(CONF_HOST, "")

            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            connector = user_input.get(CONF_CONNECTOR, DEFAULT_CONNECTOR)

            if not host:
                errors["base"] = "no_host"
            else:
                client = CharxModbusClient(host, port, DEFAULT_SLAVE, connector)
                try:
                    connected = await client.connect()
                    if not connected:
                        errors["base"] = "cannot_connect"
                    else:
                        global_data = await client.read_global_data()
                        await client.close()

                        self._charx_host = host
                        self._charx_port = port
                        self._charx_connector = connector
                        self._charx_device_name = (
                            global_data.device_name or f"CHARX ({host})"
                        )

                        return await self.async_step_p1_choice()
                except Exception:
                    _LOGGER.exception("Error connecting to CHARX")
                    errors["base"] = "cannot_connect"
                finally:
                    await client.close()

        # Build schema — show dropdown if we discovered chargers
        schema_fields: dict = {}
        if self._charx_discovered:
            options = {
                ip: f"{name} ({ip})"
                for ip, name in self._charx_discovered.items()
            }
            options["manual"] = "Enter IP address manually"
            schema_fields[vol.Required("discovered_charger")] = vol.In(options)

        schema_fields[vol.Optional(CONF_HOST, default="")] = str
        schema_fields[vol.Optional(CONF_PORT, default=DEFAULT_PORT)] = int
        schema_fields[
            vol.Optional(CONF_CONNECTOR, default=DEFAULT_CONNECTOR)
        ] = vol.All(int, vol.Range(min=1, max=8))

        return self.async_show_form(
            step_id="charger",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "discovered_count": str(len(self._charx_discovered)),
            },
        )

    # ── Step 3: P1 meter choice ──────────────────────────────────────

    async def async_step_p1_choice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: Ask if user wants to add a P1 meter."""
        if user_input is not None:
            if user_input.get(CONF_P1_ENABLED, False):
                await self._discover_p1_meters()
                return await self.async_step_p1_setup()
            else:
                return self._create_final_entry()

        return self.async_show_form(
            step_id="p1_choice",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_P1_ENABLED, default=False): bool,
                }
            ),
        )

    # ── Step 4: P1 meter setup ───────────────────────────────────────

    async def async_step_p1_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: Configure the P1 meter connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            p1_host = user_input.get(CONF_P1_HOST, "")

            if not p1_host and user_input.get("discovered_device"):
                p1_host = user_input["discovered_device"]

            if p1_host:
                client = P1Client(p1_host)
                try:
                    if await client.test_connection():
                        self._p1_host = p1_host
                        return self._create_final_entry()
                    else:
                        errors["base"] = "p1_cannot_connect"
                except Exception:
                    errors["base"] = "p1_cannot_connect"
                finally:
                    await client.close()
            else:
                errors["base"] = "p1_no_host"

        schema_fields: dict = {}
        if self._p1_discovered:
            options = {
                ip: f"{ip} ({serial})"
                for serial, ip in self._p1_discovered.items()
            }
            options["manual"] = "Enter IP address manually"
            schema_fields[vol.Optional("discovered_device")] = vol.In(options)

        schema_fields[vol.Optional(CONF_P1_HOST, default="")] = str

        return self.async_show_form(
            step_id="p1_setup",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "discovered_count": str(len(self._p1_discovered)),
            },
        )

    # ── Zeroconf discovery entry point ───────────────────────────────

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery — abort since we use our own scan."""
        return self.async_abort(reason="not_veton_device")

    # ── Helpers ───────────────────────────────────────────────────────

    async def _discover_charx(self) -> None:
        """Find CHARX controllers by hostname resolution + subnet scan.

        1. Try resolving known hostnames (ev3000, charx, charx-sec) — fast
        2. If nothing found, fall back to scanning subnets for Modbus port 502
        """
        # Phase 1: Try hostname resolution (very fast)
        await self._try_hostnames()

        if self._charx_discovered:
            _LOGGER.info(
                "Found %d CHARX via hostname, skipping subnet scan",
                len(self._charx_discovered),
            )
            return

        # Phase 2: Subnet scan as fallback
        _LOGGER.info("No CHARX found by hostname, scanning subnets...")
        await self._scan_subnets()

    async def _try_hostnames(self) -> None:
        """Try resolving known CHARX hostnames to IP addresses."""
        loop = asyncio.get_event_loop()

        async def _resolve_and_probe(hostname: str) -> None:
            try:
                ip = await loop.run_in_executor(
                    None, lambda: socket.gethostbyname(hostname)
                )
                _LOGGER.debug("Hostname %s resolved to %s", hostname, ip)
                name = await self._probe_modbus_device(ip)
                if name:
                    self._charx_discovered[ip] = name
                    _LOGGER.info(
                        "Discovered CHARX via hostname %s at %s: %s",
                        hostname, ip, name,
                    )
            except socket.gaierror:
                _LOGGER.debug("Hostname %s not found", hostname)
            except Exception:
                _LOGGER.debug("Failed to probe hostname %s", hostname)

        await asyncio.gather(
            *[_resolve_and_probe(h) for h in _CHARX_HOSTNAMES]
        )

    async def _scan_subnets(self) -> None:
        """Scan common subnets for Modbus port 502."""
        subnets = set(_COMMON_SUBNETS)
        try:
            hostname = socket.gethostname()
            local_ip = await asyncio.get_event_loop().run_in_executor(
                None, lambda: socket.gethostbyname(hostname)
            )
            local_subnet = local_ip.rsplit(".", 1)[0]
            subnets.add(local_subnet)
        except Exception:
            pass

        for subnet in subnets:
            try:
                sem = asyncio.Semaphore(30)

                async def _limited_probe(ip: str) -> None:
                    async with sem:
                        await self._probe_modbus_host(ip)

                tasks = [
                    _limited_probe(f"{subnet}.{i}") for i in range(1, 255)
                ]
                await asyncio.gather(*tasks)
            except Exception:
                _LOGGER.debug("CHARX scan failed for subnet %s", subnet)

    async def _probe_modbus_host(self, ip: str) -> None:
        """Check if host has Modbus on port 502 and read device name."""
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 502), timeout=0.5
            )
            writer.close()
            await writer.wait_closed()
        except Exception:
            return

        # Port is open — read device name
        name = await self._probe_modbus_device(ip)
        if name:
            self._charx_discovered[ip] = name
            _LOGGER.info("Discovered CHARX at %s: %s", ip, name)

    async def _probe_modbus_device(self, ip: str) -> str | None:
        """Read CHARX device name from Modbus register 100. Returns name or None."""
        try:
            client = AsyncModbusTcpClient(ip, port=502)
            if not await asyncio.wait_for(client.connect(), timeout=2):
                return None
            result = await client.read_holding_registers(
                address=100, count=10, device_id=1
            )
            client.close()
            if result.isError():
                return None
            raw = b""
            for reg in result.registers:
                raw += struct.pack(">H", reg)
            name = raw.decode("ascii", errors="replace").rstrip("\x00").strip()
            return name if name else None
        except Exception:
            return None

    async def _discover_p1_meters(self) -> None:
        """Find HomeWizard P1 meters by probing the CHARX subnet."""
        parts = self._charx_host.rsplit(".", 1)
        if len(parts) != 2:
            return
        subnet = parts[0]

        async def _probe(session: aiohttp.ClientSession, ip: str) -> None:
            try:
                async with session.get(
                    f"http://{ip}/api",
                    timeout=aiohttp.ClientTimeout(total=1),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        product = data.get("product_type", "")
                        serial = data.get("serial", ip)
                        if "HWE-P1" in product or "energy" in product.lower():
                            self._p1_discovered[serial] = ip
                            _LOGGER.debug(
                                "Discovered P1 meter at %s: %s", ip, product
                            )
            except Exception:
                pass

        try:
            connector = aiohttp.TCPConnector(limit=20)
            async with aiohttp.ClientSession(connector=connector) as session:
                for batch_start in range(1, 255, 20):
                    batch = [
                        _probe(session, f"{subnet}.{i}")
                        for i in range(batch_start, min(batch_start + 20, 255))
                    ]
                    await asyncio.gather(*batch)
        except Exception:
            _LOGGER.debug("P1 network discovery failed")

    def _create_final_entry(self) -> ConfigFlowResult:
        """Create the config entry with all collected data."""
        unique_id = (
            f"{self._charx_host}:{self._charx_port}:{self._charx_connector}"
        )
        self._abort_if_unique_id_configured()

        data = {
            CONF_HOST: self._charx_host,
            CONF_PORT: self._charx_port,
            CONF_CONNECTOR: self._charx_connector,
            CONF_P1_ENABLED: bool(self._p1_host),
            CONF_P1_HOST: self._p1_host,
        }

        title = f"Veton Charger - {self._charx_device_name}"
        if self._p1_host:
            title += " + P1"

        return self.async_create_entry(title=title, data=data)
