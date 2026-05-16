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

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

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

    async def _async_update_method():
        """Get data from Sensirion SHT31 BLE."""
        ble_device = bluetooth.async_ble_device_from_address(hass, address)
        if not ble_device:
            raise UpdateFailed(
                f"Could not find Sensirion SHT31 device with address {address}"
            )

        try:
            data = await sht31.update_device(ble_device, sht31_device=sht31_device)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update_method,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

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
