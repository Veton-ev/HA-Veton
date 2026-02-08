"""First-boot helper: triggers Veton config flow after onboarding.

This module registers a one-time listener for EVENT_HOMEASSISTANT_STARTED.
When HA starts and no Veton config entries exist, it creates a config flow
so the user sees "Veton EV Charger" in their notifications immediately.

Called from __init__.py:async_setup().
"""

from __future__ import annotations

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "veton"


def async_register(hass: HomeAssistant) -> None:
    """Register a one-time listener to auto-trigger the Veton config flow."""

    async def _on_ha_started(event: Event) -> None:
        """Create config flow when HA is fully started."""
        if hass.config_entries.async_entries(DOMAIN):
            return  # Already configured

        _LOGGER.info("First boot detected — starting Veton setup wizard")
        await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "onboarding"}
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_ha_started)
