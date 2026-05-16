"""Parser for Sensirion SHT31 BLE devices"""

from __future__ import annotations

import dataclasses
import struct
import logging
from typing import Optional

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

DEVICE_INFO_UUID = "180A"
DEVICE_INFO_CHAR_UUIDS = {
    "00002a23-0000-1000-8000-00805f9b34fb": "identifier",
    "00002a24-0000-1000-8000-00805f9b34fb": "model",
    "00002a25-0000-1000-8000-00805f9b34fb": "serial",
    "00002a26-0000-1000-8000-00805f9b34fb": "firmware_revision",
    "00002a27-0000-1000-8000-00805f9b34fb": "hardware_revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "software_revision",
    "00002a29-0000-1000-8000-00805f9b34fb": "manufacturer",
}
BATTERY_UUID = "180F"
BATTERY_CHAR_UUID = "2A19"
HUMIDITY_UUID = "00001234-b38d-4985-720e-0f993a68ee41"
HUMIDITY_CHAR_UUID = "00001235-b38d-4985-720e-0f993a68ee41"
TEMPERATURE_UUID = "00002234-b38d-4985-720e-0f993a68ee41"
TEMPERATURE_CHAR_UUID = "00002235-b38d-4985-720e-0f993a68ee41"

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class SHT31Device:
    """Response data with information about the Sensirion SHT31 BLE device"""

    firmware_revision: str = ""
    name: str = ""
    advertised_name: str = ""
    identifier: str = ""
    address: str = ""
    manufacturer: str = ""
    model: str = ""
    serial: str = ""
    hardware_revision: str = ""
    software_revision: str = ""
    sensors: dict[str, str | float | None] = dataclasses.field(
        default_factory=lambda: {}
    )


class SHT31BluetoothDeviceData:
    """Data for Sensirion SHT31 BLE sensors."""

    def __init__(
        self,
        logger: logging.Logger,
    ):
        super().__init__()
        self.logger = logger
        self.logger.debug("In Device Data")

    def decode_temperature(self, data: bytes) -> float:
        temperature = struct.unpack("<f", data)[0]
        return round(temperature, 2)

    def decode_humidity(self, data: bytes) -> float:
        humidity = struct.unpack("<f", data)[0]
        return round(humidity, 2)

    async def _get_device_info(self, client: BleakClient, device: SHT31Device) -> None:
        _LOGGER.debug("Getting Device Info")

        for char_uuid, attribute in DEVICE_INFO_CHAR_UUIDS.items():
            try:
                value = await client.read_gatt_char(char_uuid)
                if attribute == "identifier":
                    decoded_value = value.hex()
                else:
                    decoded_value = value.decode("utf-8").rstrip("\x00")
                setattr(device, attribute, decoded_value)
                _LOGGER.debug(f"Got {attribute}: {decoded_value}")
            except Exception as e:
                _LOGGER.error(f"Error reading {attribute}: {e}")

    async def _get_battery(self, client: BleakClient, device: SHT31Device) -> None:
        _LOGGER.debug("Getting Battery Level")
        battery_level = await client.read_gatt_char(BATTERY_CHAR_UUID)
        device.sensors["battery"] = int(battery_level[0])

    async def _get_humidity(self, client: BleakClient, device: SHT31Device) -> None:
        _LOGGER.debug("Getting Humidity")
        humidity_data = await client.read_gatt_char(HUMIDITY_CHAR_UUID)
        device.sensors["humidity"] = self.decode_humidity(humidity_data)

    async def _get_temperature(self, client: BleakClient, device: SHT31Device) -> None:
        _LOGGER.debug("Getting Temperature")
        temperature_data = await client.read_gatt_char(TEMPERATURE_CHAR_UUID)
        device.sensors["temperature"] = self.decode_temperature(temperature_data)

    async def initialize_device(self, ble_device: BLEDevice) -> SHT31Device:
        """Initializes the device by retrieving device info"""
        _LOGGER.debug("Initializing Device")
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        _LOGGER.debug("Got Client")
        device = SHT31Device()
        _LOGGER.debug("Made Device")

        await self._get_device_info(client, device)
        device.name = "Sensirion SHT31"
        device.advertised_name = ble_device.name
        device.address = ble_device.address
        _LOGGER.debug("device.name: %s", device.name)
        _LOGGER.debug("device.advertised_name: %s", device.advertised_name)
        _LOGGER.debug("device.address: %s", device.address)

        await client.disconnect()

        return device

    async def update_device(
        self, ble_device: BLEDevice, sht31_device: Optional[SHT31Device] = None
    ) -> SHT31Device:
        """Connects to the device through BLE and retrieves relevant data"""
        _LOGGER.debug("Update Device")
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        _LOGGER.debug("Got Client")
        if sht31_device is not None:
            device = sht31_device
        _LOGGER.debug("Made Device")

        await self._get_battery(client, device)
        await self._get_humidity(client, device)
        await self._get_temperature(client, device)
        if sht31_device is None:
            device.name = "Sensirion SHT31"
            device.advertised_name = ble_device.name
            device.address = ble_device.address
        _LOGGER.debug("device.name: %s", device.name)
        _LOGGER.debug("device.advertised_name: %s", device.advertised_name)
        _LOGGER.debug("device.address: %s", device.address)

        await client.disconnect()

        return device
