"""Support for Sensirion SHT31 BLE sensors."""
from __future__ import annotations

from .ble_sht31 import SHT31Device
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import SHT31ConfigEntry

SENSORS_MAPPING_TEMPLATE: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "humidity": SensorEntityDescription(
        key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery": SensorEntityDescription(
        key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SHT31ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SHT31 BLE sensors."""
    coordinator = entry.runtime_data.coordinator
    battery_coordinator = entry.runtime_data.battery_coordinator
    entities = []
    for sensor_type, description in SENSORS_MAPPING_TEMPLATE.items():
        if sensor_type == "battery":
            entities.append(
                SHT31Sensor(battery_coordinator, coordinator.data, description)
            )
        else:
            entities.append(
                SHT31Sensor(coordinator, coordinator.data, description)
            )

    async_add_entities(entities)


class SHT31Sensor(CoordinatorEntity[DataUpdateCoordinator[SHT31Device]], SensorEntity):
    """Sensirion SHT31 BLE sensors for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        sht31_device: SHT31Device,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the SHT31 entity with relevant data."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        if entity_description.key == "battery":
            self._attr_force_update = True

        self._attr_unique_id = f"{sht31_device.address}_{entity_description.key}"

        self._attr_device_info = DeviceInfo(
            connections={
                (CONNECTION_BLUETOOTH, sht31_device.address)
            },
            name=f"{sht31_device.name} {sht31_device.identifier}",
            manufacturer=sht31_device.manufacturer,
            model=sht31_device.model,
            hw_version=sht31_device.hardware_revision,
            sw_version=sht31_device.software_revision,
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        try:
            return self.coordinator.data.sensors[self.entity_description.key]
        except KeyError:
            return None
