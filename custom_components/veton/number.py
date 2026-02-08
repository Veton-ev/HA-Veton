"""Number entities for Veton EV Charger."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VetonCoordinator
from .ems import EmsController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator: VetonCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    ems: EmsController | None = hass.data[DOMAIN][entry.entry_id].get("ems")

    entities: list[NumberEntity] = [
        VetonMaxCurrentNumber(coordinator, entry),
    ]

    # Add EMS tuning numbers if P1 meter is available
    if ems is not None:
        entities.extend([
            EmsMaxSiteCurrentNumber(coordinator, entry, ems),
            EmsMaxChargerCurrentNumber(coordinator, entry, ems),
            EmsMinSolarSurplusNumber(coordinator, entry, ems),
            EmsSolarMarginNumber(coordinator, entry, ems),
            EmsCheapHoursNumber(coordinator, entry, ems),
        ])

    async_add_entities(entities)


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


# ── EMS configuration numbers ───────────────────────────────────────


class _EmsNumberBase(CoordinatorEntity[VetonCoordinator], NumberEntity):
    """Base for EMS setting numbers."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: VetonCoordinator, entry: ConfigEntry, ems: EmsController
    ) -> None:
        super().__init__(coordinator)
        self._ems = ems
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }


class EmsMaxSiteCurrentNumber(_EmsNumberBase):
    """Max current per phase for the mains fuse (capacity limitation)."""

    _attr_name = "EMS max site current"
    _attr_icon = "mdi:fuse"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 10
    _attr_native_max_value = 63
    _attr_native_step = 1

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator, entry, ems)
        self._attr_unique_id = f"{entry.entry_id}_ems_max_site_current"

    @property
    def native_value(self) -> float:
        return self._ems.settings.max_site_current_a

    async def async_set_native_value(self, value: float) -> None:
        self._ems.settings.max_site_current_a = int(value)
        self.async_write_ha_state()


class EmsMaxChargerCurrentNumber(_EmsNumberBase):
    """Max current the EMS will ever set for the charger."""

    _attr_name = "EMS max charger current"
    _attr_icon = "mdi:car-electric"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6
    _attr_native_max_value = 32
    _attr_native_step = 1

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator, entry, ems)
        self._attr_unique_id = f"{entry.entry_id}_ems_max_charger_current"

    @property
    def native_value(self) -> float:
        return self._ems.settings.max_charger_current_a

    async def async_set_native_value(self, value: float) -> None:
        self._ems.settings.max_charger_current_a = int(value)
        self.async_write_ha_state()


class EmsMinSolarSurplusNumber(_EmsNumberBase):
    """Minimum solar surplus (W) before starting to charge."""

    _attr_name = "EMS min solar surplus"
    _attr_icon = "mdi:solar-power"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 500
    _attr_native_max_value = 10000
    _attr_native_step = 100

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator, entry, ems)
        self._attr_unique_id = f"{entry.entry_id}_ems_min_solar_surplus"

    @property
    def native_value(self) -> float:
        return self._ems.settings.min_solar_surplus_w

    async def async_set_native_value(self, value: float) -> None:
        self._ems.settings.min_solar_surplus_w = int(value)
        self.async_write_ha_state()


class EmsSolarMarginNumber(_EmsNumberBase):
    """Extra margin (W) above min surplus before resuming charge."""

    _attr_name = "EMS solar margin"
    _attr_icon = "mdi:arrow-expand-horizontal"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_max_value = 2000
    _attr_native_step = 50

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator, entry, ems)
        self._attr_unique_id = f"{entry.entry_id}_ems_solar_margin"

    @property
    def native_value(self) -> float:
        return self._ems.settings.solar_margin_w

    async def async_set_native_value(self, value: float) -> None:
        self._ems.settings.solar_margin_w = int(value)
        self.async_write_ha_state()


class EmsCheapHoursNumber(_EmsNumberBase):
    """Number of cheapest hours to charge in per day."""

    _attr_name = "EMS cheap hours"
    _attr_icon = "mdi:clock-time-four"
    _attr_native_min_value = 1
    _attr_native_max_value = 24
    _attr_native_step = 1

    def __init__(self, coordinator, entry, ems) -> None:
        super().__init__(coordinator, entry, ems)
        self._attr_unique_id = f"{entry.entry_id}_ems_cheap_hours"

    @property
    def native_value(self) -> float:
        return self._ems.settings.cheap_hours_count

    async def async_set_native_value(self, value: float) -> None:
        self._ems.settings.cheap_hours_count = int(value)
        self.async_write_ha_state()
