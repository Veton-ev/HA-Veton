"""Number entities for Veton EV Charger."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
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
    """Set up number entities."""
    coordinator: VetonCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([VetonMaxCurrentNumber(coordinator, entry)])


class VetonMaxCurrentNumber(CoordinatorEntity[VetonCoordinator], NumberEntity):
    """Number entity to set max charging current (register X301)."""

    _attr_has_entity_name = True
    _attr_name = "Max charging current"
    _attr_icon = "mdi:current-ac"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6
    _attr_native_max_value = 80
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: VetonCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_max_current"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        if coordinator.data:
            cfg_max = coordinator.data.connector_data.max_current_setting
            if 6 <= cfg_max <= 80:
                self._attr_native_max_value = cfg_max

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.connector_data.max_current_a

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_max_current(int(value))
        await self.coordinator.async_request_refresh()
