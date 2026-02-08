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
from .ems import EmsController, EmsResult
from .tariff_client import TariffData


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
        value_fn=None,  # handled specially
    ),
)

# ── P1 Meter sensors (only created when P1 is configured) ────────

P1_SENSORS: tuple[VetonSensorDescription, ...] = (
    VetonSensorDescription(
        key="p1_grid_power",
        name="Grid power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        icon="mdi:transmission-tower",
        value_fn=lambda d: d.p1_data.active_power_w if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_grid_power_l1",
        name="Grid power L1",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.p1_data.active_power_l1_w if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_grid_power_l2",
        name="Grid power L2",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.p1_data.active_power_l2_w if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_grid_power_l3",
        name="Grid power L3",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda d: d.p1_data.active_power_l3_w if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_total_import",
        name="Grid total import",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.p1_data.total_power_import_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_total_export",
        name="Grid total export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.p1_data.total_power_export_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_import_t1",
        name="Grid import tariff 1",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.total_power_import_t1_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_import_t2",
        name="Grid import tariff 2",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.total_power_import_t2_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_export_t1",
        name="Grid export tariff 1",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.total_power_export_t1_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_export_t2",
        name="Grid export tariff 2",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.total_power_export_t2_kwh if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_voltage_l1",
        name="Grid voltage L1",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_voltage_l1_v if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_voltage_l2",
        name="Grid voltage L2",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_voltage_l2_v if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_voltage_l3",
        name="Grid voltage L3",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_voltage_l3_v if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_current_l1",
        name="Grid current L1",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_current_l1_a if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_current_l2",
        name="Grid current L2",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_current_l2_a if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_current_l3",
        name="Grid current L3",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.p1_data.active_current_l3_a if d.p1_data else None,
    ),
    VetonSensorDescription(
        key="p1_peak_demand",
        name="Grid peak demand",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        icon="mdi:chart-bar",
        value_fn=lambda d: d.p1_data.monthly_power_peak_w if d.p1_data and d.p1_data.monthly_power_peak_w else None,
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

    entities: list[VetonSensor] = []
    for description in CONNECTOR_SENSORS:
        entities.append(VetonSensor(coordinator, entry, description, session_tracker))

    # Add P1 meter sensors if configured
    if coordinator.has_p1:
        for description in P1_SENSORS:
            entities.append(VetonSensor(
                coordinator, entry, description, session_tracker,
                device_name="Mains Meter (P1)",
                device_id_suffix="_p1",
            ))

    # Add EMS diagnostic sensors if EMS is active
    ems = hass.data[DOMAIN][entry.entry_id].get("ems")
    if ems is not None:
        for description in EMS_SENSORS:
            entities.append(VetonEmsSensor(coordinator, entry, description, ems))

    # Add tariff sensors if tariff client is active
    if coordinator.has_tariffs:
        for description in TARIFF_SENSORS:
            entities.append(VetonTariffSensor(coordinator, entry, description))

    async_add_entities(entities)


class VetonSensor(CoordinatorEntity[VetonCoordinator], SensorEntity):
    """A sensor entity for the CHARX charger or P1 meter."""

    entity_description: VetonSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VetonCoordinator,
        entry: ConfigEntry,
        description: VetonSensorDescription,
        session_tracker,
        device_name: str | None = None,
        device_id_suffix: str = "",
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._session_tracker = session_tracker
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        device_id = f"{entry.entry_id}{device_id_suffix}"
        if device_id_suffix:
            # P1 meter device
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
                "name": device_name or "Mains Meter",
                "manufacturer": "HomeWizard",
                "model": "P1 Meter",
                "via_device": (DOMAIN, entry.entry_id),
            }
        else:
            # Charger device
            self._attr_device_info = {
                "identifiers": {(DOMAIN, device_id)},
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


# ── EMS diagnostic sensors ──────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class EmsEmsSensorDescription(SensorEntityDescription):
    """Describe an EMS diagnostic sensor."""

    ems_value_fn: Callable[[EmsResult], float | int | str | None]


EMS_SENSORS: tuple[EmsEmsSensorDescription, ...] = (
    EmsEmsSensorDescription(
        key="ems_target_current",
        name="EMS target current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:target",
        ems_value_fn=lambda r: r.target_current_a,
    ),
    EmsEmsSensorDescription(
        key="ems_solar_surplus",
        name="EMS solar surplus",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        icon="mdi:solar-power",
        ems_value_fn=lambda r: round(r.solar_surplus_w),
    ),
    EmsEmsSensorDescription(
        key="ems_available_site_current",
        name="EMS available site current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        icon="mdi:fuse",
        ems_value_fn=lambda r: round(r.available_site_current_a, 1),
    ),
    EmsEmsSensorDescription(
        key="ems_status",
        name="EMS status",
        icon="mdi:information-outline",
        ems_value_fn=lambda r: r.reason,
    ),
    EmsEmsSensorDescription(
        key="ems_charging",
        name="EMS charging active",
        icon="mdi:ev-station",
        ems_value_fn=lambda r: "Yes" if r.should_charge else "No",
    ),
)


class VetonEmsSensor(CoordinatorEntity[VetonCoordinator], SensorEntity):
    """Sensor that reads from the EMS controller's last result."""

    entity_description: EmsEmsSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VetonCoordinator,
        entry: ConfigEntry,
        description: EmsEmsSensorDescription,
        ems: EmsController,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._ems = ems
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> float | int | str | None:
        return self.entity_description.ems_value_fn(self._ems.last_result)


# ── Tariff sensors ──────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class TariffSensorDescription(SensorEntityDescription):
    """Describe a tariff sensor."""

    tariff_value_fn: Callable[[TariffData | None], float | int | str | None]


TARIFF_SENSORS: tuple[TariffSensorDescription, ...] = (
    TariffSensorDescription(
        key="tariff_current_price",
        name="Electricity price",
        icon="mdi:currency-eur",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=4,
        tariff_value_fn=lambda d: d.current_price if d else None,
    ),
    TariffSensorDescription(
        key="tariff_today_min",
        name="Electricity price today min",
        icon="mdi:arrow-down-bold",
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=4,
        tariff_value_fn=lambda d: d.today_min if d else None,
    ),
    TariffSensorDescription(
        key="tariff_today_max",
        name="Electricity price today max",
        icon="mdi:arrow-up-bold",
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=4,
        tariff_value_fn=lambda d: d.today_max if d else None,
    ),
    TariffSensorDescription(
        key="tariff_today_avg",
        name="Electricity price today avg",
        icon="mdi:approximately-equal",
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=4,
        tariff_value_fn=lambda d: d.today_avg if d else None,
    ),
    TariffSensorDescription(
        key="tariff_tomorrow_available",
        name="Tomorrow prices available",
        icon="mdi:calendar-clock",
        tariff_value_fn=lambda d: "Yes" if d and d.has_tomorrow else "No",
    ),
    TariffSensorDescription(
        key="tariff_is_cheap",
        name="Electricity price is cheap",
        icon="mdi:cash-check",
        tariff_value_fn=lambda d: "Yes" if d and d.is_cheap_now() else "No",
    ),
    TariffSensorDescription(
        key="tariff_source",
        name="Tariff source",
        icon="mdi:database",
        entity_registry_enabled_default=False,
        tariff_value_fn=lambda d: d.source if d else "unavailable",
    ),
)


class VetonTariffSensor(CoordinatorEntity[VetonCoordinator], SensorEntity):
    """Sensor for electricity tariff data."""

    entity_description: TariffSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VetonCoordinator,
        entry: ConfigEntry,
        description: TariffSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> float | int | str | None:
        tariff_data = self.coordinator.data.tariff_data if self.coordinator.data else None
        return self.entity_description.tariff_value_fn(tariff_data)

    @property
    def extra_state_attributes(self) -> dict | None:
        """Add upcoming cheap hours as an attribute for the price sensor."""
        if self.entity_description.key != "tariff_current_price":
            return None
        tariff_data = self.coordinator.data.tariff_data if self.coordinator.data else None
        if not tariff_data:
            return None
        cheapest = tariff_data.cheapest_hours(6)
        return {
            "cheapest_upcoming_hours": [
                {"start": h.start.isoformat(), "price": h.price}
                for h in cheapest
            ],
        }
