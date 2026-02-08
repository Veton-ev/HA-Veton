"""Switch entities for Veton EV Charger."""

from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VetonCoordinator


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


class VetonChargeEnableSwitch(CoordinatorEntity[VetonCoordinator], SwitchEntity):
    """Switch to enable/disable charging (register X300)."""

    _attr_has_entity_name = True
    _attr_name = "Charging enabled"
    _attr_icon = "mdi:ev-station"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_charge_enabled"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

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


class VetonAvailabilitySwitch(CoordinatorEntity[VetonCoordinator], SwitchEntity):
    """Switch to set connector availability (register X304)."""

    _attr_has_entity_name = True
    _attr_name = "Available"
    _attr_icon = "mdi:power-plug"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_availability"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

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
