"""Parser for Sensirion SHT31 BLE devices"""

from __future__ import annotations

import dataclasses
import struct
import logging
from typing import Optional

from bleak import BleakClient, BleakError
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

    def __init__(self):
        super().__init__()
        self._client: BleakClient | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def _ensure_connected(self, ble_device: BLEDevice) -> BleakClient:
        if self.is_connected:
            return self._client
        _LOGGER.debug("Establishing BLE connection to %s", ble_device.address)
        self._client = await establish_connection(
            BleakClient, ble_device, ble_device.address
        )
        return self._client

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None

    def decode_temperature(self, data: bytes) -> float:
        return round(struct.unpack("<f", data)[0], 2)

    def decode_humidity(self, data: bytes) -> float:
        return round(struct.unpack("<f", data)[0], 2)

    async def _get_device_info(self, client: BleakClient, device: SHT31Device) -> None:
        for char_uuid, attribute in DEVICE_INFO_CHAR_UUIDS.items():
            try:
                value = await client.read_gatt_char(char_uuid)
                if attribute == "identifier":
                    decoded_value = value.hex()
                else:
                    decoded_value = value.decode("utf-8").rstrip("\x00")
                setattr(device, attribute, decoded_value)
            except BleakError as e:
                _LOGGER.error(f"Error reading {attribute}: {e}")

    async def _get_battery(self, client: BleakClient, device: SHT31Device) -> None:
        battery_level = await client.read_gatt_char(BATTERY_CHAR_UUID)
        device.sensors["battery"] = int(battery_level[0])

    async def _get_humidity(self, client: BleakClient, device: SHT31Device) -> None:
        humidity_data = await client.read_gatt_char(HUMIDITY_CHAR_UUID)
        device.sensors["humidity"] = self.decode_humidity(humidity_data)

    async def _get_temperature(self, client: BleakClient, device: SHT31Device) -> None:
        temperature_data = await client.read_gatt_char(TEMPERATURE_CHAR_UUID)
        device.sensors["temperature"] = self.decode_temperature(temperature_data)

    async def initialize_device(self, ble_device: BLEDevice) -> SHT31Device:
        """Connects and retrieves device info, keeping the connection open."""
        client = await self._ensure_connected(ble_device)
        device = SHT31Device()

        await self._get_device_info(client, device)
        device.name = "Sensirion SHT31"
        device.advertised_name = ble_device.name
        device.address = ble_device.address

        return device

    async def update_device(
        self, ble_device: BLEDevice, sht31_device: Optional[SHT31Device] = None
    ) -> SHT31Device:
        """Reads sensor data, reconnecting if needed."""
        client = await self._ensure_connected(ble_device)
        if sht31_device is not None:
            device = sht31_device
        else:
            device = SHT31Device()
            device.name = "Sensirion SHT31"
            device.advertised_name = ble_device.name
            device.address = ble_device.address

        await self._get_battery(client, device)
        await self._get_humidity(client, device)
        await self._get_temperature(client, device)

        return device
