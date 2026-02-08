"""Veton Setup Helper — auto-configures Veton integration on first boot.

This tiny integration is loaded via configuration.yaml (veton_setup:).
It waits for HA to fully start, then:
1. Discovers CHARX controllers (hostname resolution + subnet scan)
2. Discovers HomeWizard P1 meters (HTTP API probe)
3. Creates the Veton config entry automatically via SOURCE_IMPORT
4. No user interaction required — fully turnkey for Raspberry Pi installs

On the Raspberry Pi image, configuration.yaml includes:
    veton_setup:
"""

import asyncio
import logging
import socket
import struct
from typing import Any

import aiohttp
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)
VETON_DOMAIN = "veton"

# Known CHARX hostnames to try resolving
_CHARX_HOSTNAMES = ["ev3000", "charx", "charx-sec"]

# Common subnets to scan as fallback
_COMMON_SUBNETS = ["192.168.0", "192.168.1", "192.168.2", "10.0.0", "10.0.1"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register a one-time listener to auto-configure Veton on first boot."""

    async def _on_started(event: Event) -> None:
        if hass.config_entries.async_entries(VETON_DOMAIN):
            _LOGGER.debug("Veton already configured, skipping auto-setup")
            return

        _LOGGER.info("Veton not configured — starting auto-discovery")

        # Phase 1: Discover CHARX controller
        charx = await _discover_charx(hass)
        if not charx:
            _LOGGER.warning(
                "No CHARX controller found on the network. "
                "Add the Veton integration manually via Settings > Integrations."
            )
            _notify(hass, "no_charger")
            return

        charx_ip, charx_name = charx
        _LOGGER.info("Found CHARX at %s (%s)", charx_ip, charx_name)

        # Phase 2: Discover P1 meter on the same subnet
        p1_ip = await _discover_p1(charx_ip)
        if p1_ip:
            _LOGGER.info("Found P1 meter at %s", p1_ip)
        else:
            _LOGGER.info("No P1 meter found, continuing without it")

        # Phase 3: Create config entry via import (no UI needed)
        import_data = {
            "host": charx_ip,
            "port": 502,
            "connector": 1,
            "p1_enabled": bool(p1_ip),
            "p1_host": p1_ip or "",
            "tariff_enabled": True,
            "device_name": charx_name,
        }

        result = await hass.config_entries.flow.async_init(
            VETON_DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=import_data,
        )

        if result.get("type") == "create_entry":
            _LOGGER.info(
                "Veton integration auto-configured: %s + %s",
                charx_name,
                f"P1 ({p1_ip})" if p1_ip else "no P1",
            )
        else:
            _LOGGER.warning(
                "Auto-configuration flow result: %s", result.get("type")
            )
            _notify(hass, "flow_failed")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
    return True


def _notify(hass: HomeAssistant, reason: str) -> None:
    """Create a persistent notification for manual setup fallback."""
    from homeassistant.components.persistent_notification import async_create

    if reason == "no_charger":
        async_create(
            hass,
            (
                "No CHARX controller was found on the network. "
                "Go to **[Settings > Devices & Services](/config/integrations)** "
                "and add the **Veton** integration manually."
            ),
            title="Veton — Charger Not Found",
            notification_id="veton_setup_required",
        )
    elif reason == "flow_failed":
        async_create(
            hass,
            (
                "Auto-configuration failed. "
                "Go to **[Settings > Devices & Services](/config/integrations)** "
                "and add the **Veton** integration manually."
            ),
            title="Veton — Setup Issue",
            notification_id="veton_setup_required",
        )


# ── Discovery helpers ─────────────────────────────────────────────


async def _discover_charx(
    hass: HomeAssistant,
) -> tuple[str, str] | None:
    """Find a CHARX controller. Returns (ip, device_name) or None."""
    # Phase 1: Try hostname resolution (fast)
    loop = asyncio.get_event_loop()
    for hostname in _CHARX_HOSTNAMES:
        try:
            ip = await loop.run_in_executor(
                None, lambda h=hostname: socket.gethostbyname(h)
            )
            _LOGGER.debug("Hostname %s resolved to %s", hostname, ip)
            name = await _read_charx_name(ip)
            if name:
                return (ip, name)
        except socket.gaierror:
            pass
        except Exception:
            _LOGGER.debug("Failed probing hostname %s", hostname, exc_info=True)

    # Phase 2: Subnet scan (slower fallback)
    _LOGGER.info("No CHARX found by hostname, scanning subnets...")
    subnets = set(_COMMON_SUBNETS)
    try:
        local_hostname = socket.gethostname()
        local_ip = await loop.run_in_executor(
            None, lambda: socket.gethostbyname(local_hostname)
        )
        subnets.add(local_ip.rsplit(".", 1)[0])
    except Exception:
        pass

    found: dict[str, str] = {}

    async def _probe(ip: str) -> None:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 502), timeout=0.5
            )
            writer.close()
            await writer.wait_closed()
        except Exception:
            return
        name = await _read_charx_name(ip)
        if name:
            found[ip] = name

    for subnet in subnets:
        sem = asyncio.Semaphore(30)

        async def _limited(ip: str) -> None:
            async with sem:
                await _probe(ip)

        await asyncio.gather(
            *[_limited(f"{subnet}.{i}") for i in range(1, 255)]
        )
        if found:
            break  # Found one, no need to scan more subnets

    if found:
        ip = next(iter(found))
        return (ip, found[ip])
    return None


async def _read_charx_name(ip: str) -> str | None:
    """Read CHARX device name from Modbus register 100."""
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


async def _discover_p1(charx_ip: str) -> str | None:
    """Find a HomeWizard P1 meter on the same subnet as the CHARX."""
    parts = charx_ip.rsplit(".", 1)
    if len(parts) != 2:
        return None
    subnet = parts[0]
    found_ip: str | None = None

    async def _probe(session: aiohttp.ClientSession, ip: str) -> None:
        nonlocal found_ip
        if found_ip:
            return
        try:
            async with session.get(
                f"http://{ip}/api",
                timeout=aiohttp.ClientTimeout(total=1),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    product = data.get("product_type", "")
                    if "HWE-P1" in product or "energy" in product.lower():
                        found_ip = ip
                        _LOGGER.debug("Found P1 meter at %s: %s", ip, product)
        except Exception:
            pass

    try:
        connector = aiohttp.TCPConnector(limit=20)
        async with aiohttp.ClientSession(connector=connector) as session:
            for batch_start in range(1, 255, 20):
                if found_ip:
                    break
                batch = [
                    _probe(session, f"{subnet}.{i}")
                    for i in range(batch_start, min(batch_start + 20, 255))
                ]
                await asyncio.gather(*batch)
    except Exception:
        _LOGGER.debug("P1 discovery failed")

    return found_ip
