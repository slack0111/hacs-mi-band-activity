# Mi Smart Band Activity
## Xiaomi Smart Band Activity Sensor

A custom components for Home Assistant HACS.

Using gattlib to connect to Mi Smart Band and read bettary level and walk activity.

### Support Devices
* Mi Smart Band 5
* Mi Smart Band 6

### Support Sensors
* Battery Level (%)
* Steps (steps)
* Calories (cal)
* Distance (m)

### Requirements
* A bluetooth interface on your host. And passthrough dbus to your Home Assistant container.
* Install these packages in your Home Assistant container.
```
apk add build-base bluez-dev glib-dev boost-python3 boost-thread boost-dev
pip install --upgrade pip
pip install pybluez
pip install gattlib
```
* Check bluetoothd is running on your host and bluetooth is power on.

### Known Issues
* Cannot support two or more devices at current stage.
* Stability issue.

## Example configuration.yaml
In order to add this component as is, add a new sensor:

Replace CA:1E:82:D5:59:7D with the MAC address of your Mi Band.
```
sensor:
  - platform: mi_band_activity
    name: Mi Smart Band 6
    address: CA:1E:82:D5:59:7D
```

## Snapshot

![This is a alt text.](https://github.com/slack0111/hacs-mi-band-activity/blob/main/snapshot.png "Here is a snapshot.")