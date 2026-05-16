"""Parser for Sensirion SHT31 BLE devices"""

from __future__ import annotations

import asyncio
import dataclasses
import struct
import logging
from collections.abc import Callable

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

DEVICE_INFO_CHAR_UUIDS = {
    "00002a23-0000-1000-8000-00805f9b34fb": "identifier",
    "00002a24-0000-1000-8000-00805f9b34fb": "model",
    "00002a25-0000-1000-8000-00805f9b34fb": "serial",
    "00002a26-0000-1000-8000-00805f9b34fb": "firmware_revision",
    "00002a27-0000-1000-8000-00805f9b34fb": "hardware_revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "software_revision",
    "00002a29-0000-1000-8000-00805f9b34fb": "manufacturer",
}
BATTERY_CHAR_UUID = "2A19"
HUMIDITY_CHAR_UUID = "00001235-b38d-4985-720e-0f993a68ee41"
TEMPERATURE_CHAR_UUID = "00002235-b38d-4985-720e-0f993a68ee41"

RECONNECT_DELAY_S = 5
MAX_RECONNECT_ATTEMPTS = 30
MAX_RECONNECT_DELAY_S = 300

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
        self._notify_callback: Callable[[SHT31Device], None] | None = None
        self._disconnect_callback: Callable[[], None] | None = None
        self._gave_up_callback: Callable[[], None] | None = None
        self._device: SHT31Device | None = None
        self._ble_device_resolver: Callable[[], BLEDevice | None] | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._shutting_down: bool = False

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def _ensure_connected(self, ble_device: BLEDevice) -> BleakClient:
        async with self._connect_lock:
            if self.is_connected:
                return self._client
            _LOGGER.debug("Establishing BLE connection to %s", ble_device.address)
            self._client = await establish_connection(
                BleakClient,
                ble_device,
                ble_device.address,
                disconnected_callback=self._on_disconnected,
            )
            return self._client

    def _on_disconnected(self, _client: BleakClient) -> None:
        address = _client.address if _client else "unknown"
        _LOGGER.warning("BLE connection lost to %s", address)
        self._client = None
        if self._shutting_down:
            return
        if self._disconnect_callback:
            self._disconnect_callback()
        if self._notify_callback and self._ble_device_resolver and self._device:
            self._reconnect_task = asyncio.ensure_future(
                self._reconnect_and_resubscribe()
            )

    async def _reconnect_and_resubscribe(self) -> None:
        attempt = 0
        while not self._shutting_down and attempt < MAX_RECONNECT_ATTEMPTS:
            delay = min(RECONNECT_DELAY_S * (2 ** attempt), MAX_RECONNECT_DELAY_S)
            await asyncio.sleep(delay)
            attempt += 1
            try:
                ble_device = self._ble_device_resolver()
                if ble_device is None:
                    _LOGGER.debug("Device not found by resolver, will retry (attempt %d/%d)", attempt, MAX_RECONNECT_ATTEMPTS)
                    continue
                await self._subscribe(ble_device, self._device)
                await self._get_battery(self._client, self._device)
                if self._notify_callback:
                    self._notify_callback(self._device)
                _LOGGER.info("Reconnected and resubscribed to %s (attempt %d)", ble_device.address, attempt)
                return
            except Exception as err:
                _LOGGER.debug("Reconnect attempt %d/%d failed: %s", attempt, MAX_RECONNECT_ATTEMPTS, err)

        if not self._shutting_down:
            _LOGGER.error("Gave up reconnecting after %d attempts", MAX_RECONNECT_ATTEMPTS)
            if self._gave_up_callback:
                self._gave_up_callback()

    async def disconnect(self) -> None:
        self._shutting_down = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
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

    def _on_temperature_notification(self, _sender: int, data: bytearray) -> None:
        if self._device is None:
            return
        self._device.sensors["temperature"] = self.decode_temperature(data)
        if self._notify_callback:
            self._notify_callback(self._device)

    def _on_humidity_notification(self, _sender: int, data: bytearray) -> None:
        if self._device is None:
            return
        self._device.sensors["humidity"] = self.decode_humidity(data)
        if self._notify_callback:
            self._notify_callback(self._device)

    async def _subscribe(self, ble_device: BLEDevice, device: SHT31Device) -> None:
        """Connect, subscribe to notifications, and arm the disconnect handler."""
        client = await self._ensure_connected(ble_device)
        await client.start_notify(TEMPERATURE_CHAR_UUID, self._on_temperature_notification)
        await client.start_notify(HUMIDITY_CHAR_UUID, self._on_humidity_notification)
        _LOGGER.debug("Subscribed to notifications on %s", ble_device.address)

    async def subscribe_notifications(
        self,
        ble_device: BLEDevice,
        device: SHT31Device,
        notify_callback: Callable[[SHT31Device], None],
        ble_device_resolver: Callable[[], BLEDevice | None],
        disconnect_callback: Callable[[], None] | None = None,
        gave_up_callback: Callable[[], None] | None = None,
    ) -> None:
        """Subscribe to temperature and humidity notifications.

        Performs an initial read to seed sensor values before subscribing.
        On disconnection, automatically reconnects and resubscribes.
        """
        self._ble_device_resolver = ble_device_resolver
        self._device = device
        self._notify_callback = notify_callback
        self._disconnect_callback = disconnect_callback
        self._gave_up_callback = gave_up_callback

        client = await self._ensure_connected(ble_device)

        temperature_data = await client.read_gatt_char(TEMPERATURE_CHAR_UUID)
        device.sensors["temperature"] = self.decode_temperature(temperature_data)
        humidity_data = await client.read_gatt_char(HUMIDITY_CHAR_UUID)
        device.sensors["humidity"] = self.decode_humidity(humidity_data)

        await self._subscribe(ble_device, device)

    async def initialize_device(self, ble_device: BLEDevice) -> SHT31Device:
        """Connects and retrieves device info, keeping the connection open."""
        client = await self._ensure_connected(ble_device)
        device = SHT31Device()

        await self._get_device_info(client, device)
        device.name = "Sensirion SHT31"
        device.advertised_name = ble_device.name
        device.address = ble_device.address

        return device

    async def poll_battery(self, ble_device: BLEDevice, device: SHT31Device) -> None:
        """Read battery level (does not support notifications)."""
        client = await self._ensure_connected(ble_device)
        await self._get_battery(client, device)
