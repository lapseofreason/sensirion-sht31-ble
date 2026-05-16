# Sensirion SHT31 BLE

Home Assistant BLE Integration for Sensirion SHT31 BLE temperature and humidity sensor.

For other Sensision sensors, see the [Home Assistant Sensirion BLE Integration](https://www.home-assistant.io/integrations/sensirion_ble/).

## Installation

1. Install this repo in HACS, then add the Sensirion SHT31 BLE integration.
2. Restart Home Assistant.
3. Turn on bluetooth on the device (press and hold the button for more than 1 second). The bluetooth icon on the device should flash.
4. Add the device by adding this integration and following the instructions to add the device.

## Configuration

Temperature and humidity are received via BLE notifications in real-time (~1 second
updates). Battery level is polled separately; the interval can be set in:
`custom_components/sensirion_sht31_ble/const.py` (default: 3600 seconds / 1 hour).

## Battery

This integration subscribes to BLE notifications on the temperature and humidity
characteristics, maintaining a persistent connection. This is the lowest-power mode
for the gadget: a connected link with ~1s connection events on a single channel uses
less radio energy than disconnected advertising every 2 seconds across 3 channels.
The notification data rides on already-scheduled connection events at zero additional cost.

## Development

Useful links:

1. [SHT31 Smart Gadget Simple BLE Profile Description](https://github.com/Sensirion/SmartGadget-Firmware/blob/master/Simple_BLE_Profile_Description.pdf)
2. [SHT31 Smart Gadget User Guide](https://sensirion.com/media/documents/429F0DF6/61643DC1/Sensirion_Humidity_Sensors_SHT3x_Smart-Gadget_User-Guide_1.pdf)
3. [SmartGadget Firmware Source](https://github.com/Sensirion/SmartGadget-Firmware)
4. [Temperature Service (notify support)](https://github.com/Sensirion/SmartGadget-Firmware/blob/master/BLE_Module_nRF51822/source/services/TemperatureService.h)
5. [Humidity Service (notify support)](https://github.com/Sensirion/SmartGadget-Firmware/blob/master/BLE_Module_nRF51822/source/services/HumidityService.h)
6. [Connection parameters & speed switching](https://github.com/Sensirion/SmartGadget-Firmware/blob/master/BLE_Module_nRF51822/source/SmartGadget.cpp)

## BLE Connection Notes

The gadget uses a **5-second supervision timeout** across all connection modes. If no BLE
traffic flows for 5 seconds, the connection drops and the device resumes advertising (BT
icon blinks). The normal connection interval is ~1 second.

To maintain a persistent connection, subscribe to **notifications** on the temperature
and/or humidity characteristics (both support `NOTIFY`). This keeps regular data flowing
over the link and prevents the supervision timeout from firing.

Connection parameters (normal/slow mode):
- Connection interval: ~975–1010 ms
- Slave latency: 0
- Supervision timeout: 5000 ms
