"""Switch entities for Veton EV Charger.

Both switches write registers that the CHARX controller only honours when the
charging release mode (X120) is **Modbus** (5). Veton chargers ship with
release mode **OCPP** (4): there OCPP owns authorisation/start/stop and the
supported EMS control is the max-charging-current register X301 (the "Max
charging current" number entity). To avoid presenting a control that silently
does nothing, these switches report themselves unavailable outside Modbus mode.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RELEASE_MODE, RELEASE_MODE_MODBUS
from .coordinator import VetonCoordinator

_LOGGER = logging.getLogger(__name__)

_INACTIVE_NOTE = (
    "Charging release is owned by OCPP on this charger; this switch only works "
    "with release mode = Modbus (X120 = 5). Use the 'Max charging current' "
    "number (X301) to steer charging from an EMS or automation."
)


class _VetonReleaseModeSwitch(CoordinatorEntity[VetonCoordinator], SwitchEntity):
    """Base class for switches that require release mode = Modbus (X120 = 5).

    Subclasses set `_register` (the register they write, for logging) and
    implement `is_on` / the turn on/off calls.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _register = "X300"

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        # Warn once per entity, not on every 5 s coordinator refresh.
        self._release_mode_warned = False

    @property
    def _release_mode(self) -> int | None:
        """Current charging release mode (register X120), or None if no data."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.connector_data.release_mode

    @property
    def available(self) -> bool:
        """Available only while the charger is in Modbus release mode."""
        if not super().available:
            return False
        mode = self._release_mode
        if mode is None:
            return False
        if mode != RELEASE_MODE_MODBUS:
            self._warn_release_mode(mode)
            return False
        return True

    def _warn_release_mode(self, mode: int) -> None:
        """Log once why this switch is inactive on this charger."""
        if self._release_mode_warned:
            return
        self._release_mode_warned = True
        _LOGGER.warning(
            "%s is unavailable: this charger has release mode = %s (X120 = %s), "
            "not Modbus (%s), so writes to %s are silently ignored by the charger. "
            "Cap charging with the 'Max charging current' number entity (X301) — "
            "that is the supported path and works in every release mode",
            self._attr_name,
            RELEASE_MODE.get(mode, "Unknown"),
            mode,
            RELEASE_MODE_MODBUS,
            self._register,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the release mode and, when inactive, why."""
        mode = self._release_mode
        attrs: dict[str, Any] = {
            "register": self._register,
            "release_mode": None if mode is None else RELEASE_MODE.get(mode, "Unknown"),
            "release_mode_value": mode,
        }
        if mode is not None and mode != RELEASE_MODE_MODBUS:
            attrs["inactive_reason"] = _INACTIVE_NOTE
        return attrs


class VetonChargeEnableSwitch(_VetonReleaseModeSwitch):
    """Charging release switch (register X300).

    Writable only when release mode (X120) is Modbus (5); on an OCPP charger
    the write is silently ignored, so the entity is shown as unavailable.
    """

    _attr_name = "Charging enabled"
    _attr_icon = "mdi:ev-station"
    _register = "X300"

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "charge_enabled")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.connector_data.charge_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_charge_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_charge_enabled(False)
        await self.coordinator.async_request_refresh()


class VetonAvailabilitySwitch(_VetonReleaseModeSwitch):
    """Connector availability switch (register X304).

    Writable only when release mode (X120) is Modbus (5); on an OCPP charger
    the write is silently ignored, so the entity is shown as unavailable.
    """

    _attr_name = "Available"
    _attr_icon = "mdi:power-plug"
    _register = "X304"

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "availability")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.connector_data.availability

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.client.set_availability(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.client.set_availability(False)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator: VetonCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        VetonChargeEnableSwitch(coordinator, entry),
        VetonAvailabilitySwitch(coordinator, entry),
    ])
