"""Config flow for Sensirion SHT31 BlE integration."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from .ble_sht31.parser import SHT31BluetoothDeviceData, SHT31Device
from bleak import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    name: str
    discovery_info: BluetoothServiceInfo
    device: SHT31Device


def get_name(device: SHT31Device) -> str:
    """Generate name with identifier for device."""

    return f"{device.name}"


class SHT31DeviceUpdateError(Exception):
    """Custom error class for device updates."""


class SHT31ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sensirion SHT31 BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: Discovery | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    async def _get_device_data(
        self, discovery_info: BluetoothServiceInfo
    ) -> SHT31Device:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address
        )
        _LOGGER.debug("in _get_device_data")
        if ble_device is None:
            _LOGGER.debug("no ble_device in _get_device_data")
            raise SHT31DeviceUpdateError("No ble_device")
        
        _LOGGER.debug("Getting Device")
        sht31 = SHT31BluetoothDeviceData(_LOGGER)
        _LOGGER.debug("Got Device")
        try:
            _LOGGER.debug("Try Update")
            data = await sht31.initialize_device(ble_device)
            _LOGGER.debug("Got Data")
        except BleakError as err:
            _LOGGER.error(
                "Error connecting to and getting data from %s: %s",
                discovery_info.address,
                err,
            )
            raise SHT31DeviceUpdateError("Failed getting device data") from err
        except Exception as err:
            _LOGGER.error(
                "Unknown error occurred from %s: %s", discovery_info.address, err
            )
            raise err
        return data

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery = self._discovered_devices[address]

            self.context["title_placeholders"] = {
                "name": discovery.name,
            }

            self._discovered_device = discovery

            return self.async_create_entry(title=discovery.name, data={})

        current_addresses = self._async_current_ids()
        service_infos = list(bluetooth.async_discovered_service_info(self.hass, connectable=True))
        for discovery_info in service_infos:
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            if discovery_info.name is None:
                continue

            if not discovery_info.name.startswith("Smart Humigadget"):
                continue

            _LOGGER.debug("Found Sensirion SHT31 Device")
            _LOGGER.debug("SHT31 discovery address: %s", address)
            _LOGGER.debug("SHT31 advertised name: %s", discovery_info.name)
            _LOGGER.debug("SHT31 manufacturer: %s", discovery_info.manufacturer_data)
            _LOGGER.debug("SHT31 advertisement: %s", discovery_info.advertisement)
            _LOGGER.debug("SHT31 device: %s", discovery_info.device)
            _LOGGER.debug("SHT31 service data: %s", discovery_info.service_data)
            _LOGGER.debug("SHT31 service uuids: %s", discovery_info.service_uuids)
            _LOGGER.debug("SHT31 rssi: %s", discovery_info.rssi)
            try:
                device = await self._get_device_data(discovery_info)
                _LOGGER.debug("Getting Device Data")
            except SHT31DeviceUpdateError:
                _LOGGER.debug("Cannot Connect")
                return self.async_abort(reason="cannot_connect")
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("Cannot Connect - Unknown")
                return self.async_abort(reason="unknown")
            _LOGGER.debug("Getting Name")
            name = get_name(device)
            self._discovered_devices[address] = Discovery(name, discovery_info, device)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        titles = {
            address: get_name(discovery.device)
            for (address, discovery) in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(titles),
                },
            ),
        )
