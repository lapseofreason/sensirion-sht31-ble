# Sensirion SHT31 BLE

Home Assistant BLE Integration for Sensirion SHT31 BLE temperature and humidity sensor.

For other Sensision sensors, see the [Home Assistant Sensirion BLE Integration](https://www.home-assistant.io/integrations/sensirion_ble/).

## Installation

1. Install this repo in HACS, then add the Sensirion SHT31 BLE integration.
2. Restart Home Assistant.
3. Turn on bluetooth on the device (press and hold the button for more than 1 second). The bluetooth icon on the device should flash.
4. Add the device by adding this integration and following the instructions to add the device.

## Configuration

The default update interval can be set in: `custom_components/sensirion_sht31_ble/const.py`
Currently set to 300 seconds (5 minutes). Change the value and restart homeassistant if want more or less often.

## Development

Useful links:

1. [SHT31 Smart Gadget Simple BLE Profile Description](https://github.com/Sensirion/SmartGadget-Firmware/blob/master/Simple_BLE_Profile_Description.pdf)
2. [SHT31 Smart Gadget User Guide](https://sensirion.com/media/documents/429F0DF6/61643DC1/Sensirion_Humidity_Sensors_SHT3x_Smart-Gadget_User-Guide_1.pdf)
