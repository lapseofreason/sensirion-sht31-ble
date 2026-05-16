"""The Sensirion SHT31 BLE integration."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
import logging

from .ble_sht31 import SHT31BluetoothDeviceData, SHT31Device

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BATTERY_POLL_INTERVAL, DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class SHT31RuntimeData:
    coordinator: DataUpdateCoordinator[SHT31Device]
    client: SHT31BluetoothDeviceData


type SHT31ConfigEntry = ConfigEntry[SHT31RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SHT31ConfigEntry) -> bool:
    """Set up Sensirion SHT31 BLE device from a config entry."""
    address = entry.unique_id
    assert address is not None

    ble_device = bluetooth.async_ble_device_from_address(hass, address)
    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find Sensirion SHT31 device with address {address}"
        )
    sht31 = SHT31BluetoothDeviceData()
    sht31_device = await sht31.initialize_device(ble_device)

    await sht31.poll_battery(ble_device, sht31_device)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=None,
        update_interval=timedelta(seconds=BATTERY_POLL_INTERVAL),
    )
    coordinator.async_set_updated_data(sht31_device)

    def _on_notification(device: SHT31Device) -> None:
        coordinator.async_set_updated_data(device)

    def _on_disconnect() -> None:
        _LOGGER.warning("SHT31 BLE disconnected, attempting reconnect")

    def _resolve_ble_device():
        return bluetooth.async_ble_device_from_address(hass, address)

    await sht31.subscribe_notifications(
        ble_device, sht31_device, _on_notification, _resolve_ble_device, _on_disconnect
    )

    async def _async_poll_battery():
        """Poll battery level (does not support notifications)."""
        ble_device = bluetooth.async_ble_device_from_address(hass, address)
        if not ble_device:
            raise UpdateFailed(
                f"Could not find Sensirion SHT31 device with address {address}"
            )
        try:
            await sht31.poll_battery(ble_device, sht31_device)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch battery: {err}") from err
        return sht31_device

    coordinator.update_method = _async_poll_battery
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SHT31RuntimeData(coordinator=coordinator, client=sht31)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SHT31ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        await entry.runtime_data.client.disconnect()
    except Exception:
        _LOGGER.debug("Error disconnecting BLE client during unload", exc_info=True)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
