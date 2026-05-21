"""Sensor entities for Veton EV Charger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ENERGY_METER_TYPE, RELEASE_MODE, VEHICLE_STATUS
from .coordinator import CharxData, VetonCoordinator


@dataclass(frozen=True, kw_only=True)
class VetonSensorDescription(SensorEntityDescription):
    """Describe a Veton sensor."""

    value_fn: Callable[[CharxData], float | int | str | None]


CONNECTOR_SENSORS: tuple[VetonSensorDescription, ...] = (
    VetonSensorDescription(
        key="vehicle_status",
        translation_key="vehicle_status",
        name="Vehicle status",
        icon="mdi:car-electric",
        value_fn=lambda d: VEHICLE_STATUS.get(d.connector_data.vehicle_status, d.connector_data.vehicle_status),
    ),
    VetonSensorDescription(
        key="vehicle_status_raw",
        translation_key="vehicle_status_raw",
        name="Vehicle status code",
        icon="mdi:car-electric",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.connector_data.vehicle_status,
    ),
    VetonSensorDescription(
        key="active_power",
        name="Charging power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.connector_data.active_power_mw / 1000 if d.connector_data.active_power_mw else 0,
    ),
    VetonSensorDescription(
        key="total_energy",
        name="Total energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        value_fn=lambda d: d.connector_data.total_energy_wh,
    ),
    VetonSensorDescription(
        key="session_energy",
        name="Session energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_display_precision=0,
        value_fn=lambda d: d.connector_data.session_energy_wh,
    ),
    VetonSensorDescription(
        key="voltage_l1",
        name="Voltage L1",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.voltage_l1_mv / 1000,
    ),
    VetonSensorDescription(
        key="voltage_l2",
        name="Voltage L2",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.voltage_l2_mv / 1000,
    ),
    VetonSensorDescription(
        key="voltage_l3",
        name="Voltage L3",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.voltage_l3_mv / 1000,
    ),
    VetonSensorDescription(
        key="current_l1",
        name="Current L1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.current_l1_ma / 1000,
    ),
    VetonSensorDescription(
        key="current_l2",
        name="Current L2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.current_l2_ma / 1000,
    ),
    VetonSensorDescription(
        key="current_l3",
        name="Current L3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda d: d.connector_data.current_l3_ma / 1000,
    ),
    VetonSensorDescription(
        key="charging_current",
        name="Charging current setting",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda d: d.connector_data.current_charge_a,
    ),
    VetonSensorDescription(
        key="connection_time",
        name="Connection time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        value_fn=lambda d: d.connector_data.connection_time_s,
    ),
    VetonSensorDescription(
        key="charging_time",
        name="Charging time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-outline",
        value_fn=lambda d: d.connector_data.charging_time_s,
    ),
    VetonSensorDescription(
        key="rfid_uid",
        name="Last RFID",
        icon="mdi:card-account-details",
        value_fn=lambda d: d.connector_data.rfid_uid or "None",
    ),
    VetonSensorDescription(
        key="evcc_id",
        name="Last EVCC ID",
        icon="mdi:identifier",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.connector_data.evcc_id or "None",
    ),
    VetonSensorDescription(
        key="error_code",
        name="Error code",
        icon="mdi:alert-circle-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda d: f"0x{d.connector_data.error_code:08X}" if d.connector_data.error_code else "None",
    ),
    VetonSensorDescription(
        key="release_mode",
        name="Release mode",
        icon="mdi:shield-key",
        entity_registry_enabled_default=False,
        value_fn=lambda d: RELEASE_MODE.get(d.connector_data.release_mode, "Unknown"),
    ),
    VetonSensorDescription(
        key="energy_meter_type",
        name="Energy meter",
        icon="mdi:meter-electric",
        entity_registry_enabled_default=False,
        value_fn=lambda d: ENERGY_METER_TYPE.get(d.connector_data.energy_meter_type, "Unknown"),
    ),
    VetonSensorDescription(
        key="session_count",
        name="Total sessions",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=None,  # handled specially via the session tracker
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: VetonCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    session_tracker = hass.data[DOMAIN][entry.entry_id]["session_tracker"]

    async_add_entities(
        VetonSensor(coordinator, entry, description, session_tracker)
        for description in CONNECTOR_SENSORS
    )


class VetonSensor(CoordinatorEntity[VetonCoordinator], SensorEntity):
    """A sensor entity for the CHARX charger."""

    entity_description: VetonSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VetonCoordinator,
        entry: ConfigEntry,
        description: VetonSensorDescription,
        session_tracker,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._session_tracker = session_tracker
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Veton",
            "model": "CHARX EV Charger",
            "sw_version": coordinator.data.global_data.software_version if coordinator.data else None,
        }

    @property
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        if self.entity_description.key == "session_count":
            return self._session_tracker.session_count
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
