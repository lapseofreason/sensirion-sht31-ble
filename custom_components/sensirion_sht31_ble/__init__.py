"""The Sensirion SHT31 BLE integration."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
import logging

from .ble_sht31 import SHT31BluetoothDeviceData, SHT31Device

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BATTERY_POLL_INTERVAL,
    CONF_STALENESS_TIMEOUT,
    DEFAULT_BATTERY_POLL_INTERVAL,
    DEFAULT_STALENESS_TIMEOUT,
    DOMAIN,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class SHT31RuntimeData:
    coordinator: DataUpdateCoordinator[SHT31Device]
    battery_coordinator: DataUpdateCoordinator[SHT31Device]
    client: SHT31BluetoothDeviceData


type SHT31ConfigEntry = ConfigEntry[SHT31RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SHT31ConfigEntry) -> bool:
    """Set up Sensirion SHT31 BLE device from a config entry."""
    address = entry.unique_id
    assert address is not None

    battery_poll_interval = entry.options.get(CONF_BATTERY_POLL_INTERVAL, DEFAULT_BATTERY_POLL_INTERVAL)
    staleness_timeout = entry.options.get(CONF_STALENESS_TIMEOUT, DEFAULT_STALENESS_TIMEOUT)

    ble_device = bluetooth.async_ble_device_from_address(hass, address)
    if not ble_device:
        raise ConfigEntryNotReady(
            f"Could not find Sensirion SHT31 device with address {address}"
        )
    sht31 = SHT31BluetoothDeviceData(loop=hass.loop)
    try:
        sht31_device = await sht31.initialize_device(ble_device)
    except Exception as err:
        await sht31.disconnect()
        raise ConfigEntryNotReady(f"Failed to initialize SHT31: {err}") from err

    try:
        await sht31.poll_battery(ble_device, sht31_device)
    except Exception:
        _LOGGER.debug("%s: initial battery read failed, will retry on next poll", address, exc_info=True)

    coordinator: DataUpdateCoordinator[SHT31Device] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{address}",
        update_method=None,
        update_interval=None,
    )
    coordinator.async_set_updated_data(sht31_device)

    battery_coordinator: DataUpdateCoordinator[SHT31Device] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{address}_battery",
        update_method=None,
        update_interval=None,
    )
    battery_coordinator.async_set_updated_data(sht31_device)

    staleness_timer_cancel: CALLBACK_TYPE | None = None

    def _cancel_staleness_timer() -> None:
        nonlocal staleness_timer_cancel
        if staleness_timer_cancel is not None:
            staleness_timer_cancel()
            staleness_timer_cancel = None

    def _reset_staleness_timer() -> None:
        nonlocal staleness_timer_cancel
        _cancel_staleness_timer()
        staleness_timer_cancel = async_call_later(
            hass, staleness_timeout, _on_stale
        )

    def _mark_unavailable() -> None:
        _LOGGER.debug("%s: marking unavailable and triggering reconnect", address)
        err = ConnectionError(f"SHT31 BLE device {address} is unavailable (no data received)")
        coordinator.async_set_update_error(err)
        battery_coordinator.async_set_update_error(err)
        sht31.trigger_reconnect()

    def _on_stale(_now=None) -> None:
        nonlocal staleness_timer_cancel
        staleness_timer_cancel = None
        _LOGGER.warning("SHT31 BLE device %s: no notifications received for %ds, marking unavailable", address, staleness_timeout)
        hass.loop.call_soon_threadsafe(_mark_unavailable)

    def _on_notification(device: SHT31Device) -> None:
        _reset_staleness_timer()
        coordinator.async_set_updated_data(device)

    def _on_battery_updated(device: SHT31Device) -> None:
        battery_coordinator.async_set_updated_data(device)

    def _on_gave_up() -> None:
        def _do_gave_up():
            _LOGGER.debug("%s: processing gave-up callback on event loop", address)
            _cancel_staleness_timer()
            err = ConnectionError(f"SHT31 BLE device {address} is unavailable")
            coordinator.async_set_update_error(err)
            battery_coordinator.async_set_update_error(err)
            _LOGGER.error("SHT31 BLE device %s: reconnect attempts exhausted", address)
        hass.loop.call_soon_threadsafe(_do_gave_up)

    def _resolve_ble_device():
        return bluetooth.async_ble_device_from_address(hass, address)

    try:
        await sht31.subscribe_notifications(
            ble_device,
            sht31_device,
            _on_notification,
            _resolve_ble_device,
            gave_up_callback=_on_gave_up,
            battery_callback=_on_battery_updated,
        )
    except Exception as err:
        await sht31.disconnect()
        raise ConfigEntryNotReady(f"Failed to subscribe to SHT31 notifications: {err}") from err

    _reset_staleness_timer()

    async def _async_poll_battery(_now=None):
        current_ble_device = bluetooth.async_ble_device_from_address(hass, address)
        try:
            await sht31.poll_battery(current_ble_device, sht31_device)
            battery_coordinator.async_set_updated_data(sht31_device)
        except Exception as err:
            _LOGGER.warning("SHT31 BLE device %s: unable to fetch battery: %s", address, err)

    entry.runtime_data = SHT31RuntimeData(coordinator=coordinator, battery_coordinator=battery_coordinator, client=sht31)

    entry.async_on_unload(
        async_track_time_interval(
            hass, _async_poll_battery, timedelta(seconds=battery_poll_interval)
        )
    )
    entry.async_on_unload(_cancel_staleness_timer)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("%s: setup complete (battery=%s)", address, "battery" in sht31_device.sensors)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SHT31ConfigEntry) -> bool:
    """Unload a config entry."""
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.client.disconnect()
    return result


async def _async_options_updated(hass: HomeAssistant, entry: SHT31ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
