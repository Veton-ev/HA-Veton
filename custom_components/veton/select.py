"""Select entities for Veton EV Charger (EMS mode)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VetonCoordinator
from .ems import EMS_MODE_DESCRIPTIONS, EmsMode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: VetonCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    ems = hass.data[DOMAIN][entry.entry_id].get("ems")
    if ems is None:
        return
    async_add_entities([VetonEmsModeSelect(coordinator, entry, ems)])


class VetonEmsModeSelect(CoordinatorEntity[VetonCoordinator], SelectEntity):
    """Select entity for EMS charging mode."""

    _attr_has_entity_name = True
    _attr_name = "Charging mode"
    _attr_icon = "mdi:solar-power-variant"
    _attr_options = [m.value for m in EmsMode]

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator)
        self._ems = ems
        self._attr_unique_id = f"{entry.entry_id}_ems_mode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def current_option(self) -> str:
        return self._ems.settings.mode.value

    async def async_select_option(self, option: str) -> None:
        self._ems.settings.mode = EmsMode(option)
        self.async_write_ha_state()
