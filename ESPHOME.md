# Sensirion SHT31 Smart Humigadget — ESPHome Setup

Alternative to the HA custom integration: read the sensor via an ESP32 running ESPHome.

## Requirements

- ESP32 with BLE support (tested with Seeed Xiao ESP32-C6)
- ESPHome with esp-idf framework
- Smart Humigadget with BLE enabled (long-press button until BT icon blinks)

## ESPHome Config (sensor-specific parts)

Add the following to your ESPHome device config. Replace `XX:XX:XX:XX:XX:XX` with
your gadget's MAC address (find it via `bluetoothctl scan le` or the Sensirion MyAmbience app).

```yaml
esp32_ble_tracker:

ble_client:
  - mac_address: "XX:XX:XX:XX:XX:XX"
    id: sht31_gadget
    on_connect:
      then:
        - binary_sensor.template.publish:
            id: sht31_connected
            state: true
    on_disconnect:
      then:
        - binary_sensor.template.publish:
            id: sht31_connected
            state: false

binary_sensor:
  - platform: template
    id: sht31_connected
    name: "SHT31 Connected"
    device_class: connectivity

sensor:
  - platform: ble_client
    ble_client_id: sht31_gadget
    name: "Temperature"
    service_uuid: "00002234-b38d-4985-720e-0f993a68ee41"
    characteristic_uuid: "00002235-b38d-4985-720e-0f993a68ee41"
    type: characteristic
    notify: true
    update_interval: never
    lambda: |-
      float value;
      memcpy(&value, x.data(), 4);
      return value;
    filters:
      - throttle: 60s
    unit_of_measurement: "°C"
    accuracy_decimals: 2
    device_class: temperature
    state_class: measurement

  - platform: ble_client
    ble_client_id: sht31_gadget
    name: "Humidity"
    service_uuid: "00001234-b38d-4985-720e-0f993a68ee41"
    characteristic_uuid: "00001235-b38d-4985-720e-0f993a68ee41"
    type: characteristic
    notify: true
    update_interval: never
    lambda: |-
      float value;
      memcpy(&value, x.data(), 4);
      return value;
    filters:
      - throttle: 60s
    unit_of_measurement: "%"
    accuracy_decimals: 2
    device_class: humidity
    state_class: measurement

  - platform: ble_client
    ble_client_id: sht31_gadget
    name: "Battery"
    service_uuid: "0000180f-0000-1000-8000-00805f9b34fb"
    characteristic_uuid: "00002a19-0000-1000-8000-00805f9b34fb"
    type: characteristic
    notify: false
    update_interval: 3600s
    lambda: |-
      return (float)x[0];
    unit_of_measurement: "%"
    accuracy_decimals: 0
    device_class: battery
    state_class: measurement
```

Also add the initial state publish in the `esphome:` block to avoid "unknown" state on boot:

```yaml
esphome:
  on_boot:
    then:
      - binary_sensor.template.publish:
          id: sht31_connected
          state: false
```

## How it works

- The ESP connects to the gadget via BLE and subscribes to GATT notifications on
  the temperature and humidity characteristics.
- The gadget sends updates every ~1 second. The `throttle: 60s` filter limits how
  often the ESP forwards data to HA (reduces WiFi traffic to ~10 MB/month).
- Battery is polled once per hour (it does not support notifications).
- On disconnect, the ESP automatically reconnects when it sees the gadget advertising.

## Notes

- **Range**: BLE range on the Xiao ESP32-C6 (PCB antenna) is limited. Keep the ESP
  within a few meters of the gadget, with line of sight if possible.
- **Single client**: The gadget only accepts one BLE connection at a time. Disconnect
  other clients (phone, HA Bluetooth integration) before the ESP will be able to connect.
