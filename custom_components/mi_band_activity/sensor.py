#!/usr/bin/env python3
import logging
import time
from datetime import datetime, timedelta
from threading import Event
import voluptuous
from gattlib import GATTRequester, GATTException, BTIOException
from homeassistant import const
from homeassistant import util
from homeassistant.helpers import config_validation
from homeassistant.helpers import entity
from homeassistant.helpers.event import track_time_change
from homeassistant.util.dt import utc_from_timestamp


REQUIREMENTS = [
    'pybluez',
    'gattlib'
]

_LOGGER = logging.getLogger(__name__)

# Sensor details.
SENSOR = 'mi_band_activity'

# Sensor base attributes.
ATTR_LAST_UPDATED = 'last_updated'
CONF_NAME = 'name'
CONF_ADDRESS = 'address'
ICON = 'mdi:watch-variant'
MIN_TIME_BETWEEN_SCANS = timedelta(minutes=5)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)
SENSOR_NAME = '{} {}'

# # Define schema of sensor.
PLATFORM_SCHEMA = config_validation.PLATFORM_SCHEMA.extend({
    voluptuous.Required(CONF_NAME): config_validation.string,
    voluptuous.Required(CONF_ADDRESS): config_validation.string,
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    name = config.get(CONF_NAME)
    address = config.get(CONF_ADDRESS)
    dev = []
    dev.append(MiBabdBatterySensor(name, address))
    add_devices(dev, True)


class Requester(GATTRequester):
    def __init__(self, wakeup, address, do_connect, device):
        super(Requester, self).__init__(address, do_connect)
        # band device
        self.device = device
        self.wakeup = wakeup

    def on_notification(self, handle, data):
        #if handle == self.device.activity_value_handle:
        #    current_time = datetime.now()
        #    print("-------- {} activity --------".format(self.device.address))
        #    print(current_time, end =" ")
        #    print("step: {}".format(int.from_bytes(data[4:8], byteorder='little')), end =" ")
        #    print("distance: {} m".format(int.from_bytes(data[8:12], byteorder='little')), end =" ")
        #    print("cal: {}".format(int.from_bytes(data[12:], byteorder='little')))
        #else:
        #    print("- notification on handle: {}".format(handle))
        #    print("data:")
        #    for i in list(data):
        #        print("0x{:02x}".format(i), end =" ")
        #    print("--------------------------------------------\n")
        self.wakeup.set()


class MiBand(object):
    DEVICE_NAME_UUID = '00002a00-0000-1000-8000-00805f9b34fb'
    SERIAL_NUMBER_UUID = '00002a25-0000-1000-8000-00805f9b34fb'
    HARDWARE_REVISION_UUID = '00002a27-0000-1000-8000-00805f9b34fb'
    SOFTWARE_REVISION_UUID = '00002a28-0000-1000-8000-00805f9b34fb'
    ACTIVITY_UUID = '00000007-0000-3512-2118-0009af100700'
    BATTERY_SERVICE_UUID = '00002a19-0000-1000-8000-00805f9b34fb'

    def __init__(self, address):
        self.received = Event()
        self.requester = Requester(self.received, address, False, self)
        self.address = address
        self.primary = None
        self.characteristic = None
        self.descriptors = None
        self.activity_handle = None
        self.activity_value_handle = None
        self.activity_notify_handle = None

    def connect(self):
        #print("Connecting...")
        self.requester.connect(True)
        if not self.requester.is_connected():
            raise BTIOException("not connected")
        #print("Succeed.")

    def wait_notification(self):
        self.received.wait(3)

    def resolve_service(self):
        #print("resolving services")
        if not self.requester.is_connected():
            raise BTIOException("not connected")
        self.primary = self.requester.discover_primary()
        self.characteristic = self.requester.discover_characteristics()
        self.descriptors = self.requester.discover_descriptors()
        #self.activity_handle = self.find_char_handle(self.ACTIVITY_UUID)
        #self.activity_value_handle = self.activity_handle + 1
        #self.activity_notify_handle = self.activity_handle + 2
        #print("done")

    def find_char_handle(self, uuid):
        for char in self.characteristic:
            if uuid == char['uuid']:
                return char['handle']
        return None

    def is_connected(self):
        return self.requester.is_connected()

    def disconnect(self):
        #print("Disconnecting...")
        if self.requester.is_connected():
            self.requester.disconnect()
        #print("Succeed.")

    def device_information(self):
        device_name = self.requester.read_by_uuid(self.DEVICE_NAME_UUID)[0]
        if not self.requester.is_connected():
            raise BTIOException("not connected")
        serial_num = self.requester.read_by_uuid(self.SERIAL_NUMBER_UUID)[0]
        hardware_rev = self.requester.read_by_uuid(self.HARDWARE_REVISION_UUID)[0]
        software_rev = self.requester.read_by_uuid(self.SOFTWARE_REVISION_UUID)[0]
        #print('device_name: {}'.format(device_name))
        #print('serial_num: {}'.format(serial_num))
        #print('hardware_rev: {}'.format(hardware_rev))
        #print('software_rev: {}'.format(software_rev))

    def activity_notifications(self, enabled=True):
        #if enabled:
        #    print('Enabling walk notifications')
        #else:
        #    print("Disabling walk rate notifications")
        if not self.requester.is_connected():
            raise BTIOException("not connected")
        self.requester.enable_notifications(self.activity_notify_handle, enabled, False)
        #print("done")

    def battery_level(self):
        data = self.requester.read_by_uuid(self.BATTERY_SERVICE_UUID)[0]
        #print("battery level: {} %".format(int.from_bytes(data, byteorder='little')))
        return int.from_bytes(data, byteorder='little')


class MiBabdSensor(entity.Entity):
    def __init__(self, name, address):
        self._name = name
        self._address = address
        self._miband = MiBand(self._address)
        self._icon = ICON
        self._name_suffix = "Mi Smart Band"
        self._state = const.STATE_UNKNOWN
        self._last_updated = const.STATE_UNKNOWN

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def last_updated(self):
        """Returns date when it was last updated."""
        if self._last_updated != const.STATE_UNKNOWN:
            stamp = float(self._last_updated)
            return utc_from_timestamp(int(stamp))

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def state_attributes(self):
        """Returns the state attributes. """
        return {
            const.ATTR_FRIENDLY_NAME: self.name,
            const.ATTR_UNIT_OF_MEASUREMENT: self.unit_of_measurement,
            ATTR_LAST_UPDATED: self._last_updated,
        }

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        return self._attributes

    @property
    def _name_suffix(self):
        """Returns the name suffix of the sensor."""
        return self._name_suffix

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        raise NotImplementedError

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        raise NotImplementedError


class MiBabdBatterySensor(MiBabdSensor):
    def __init__(self, name, address):
        super(MiBabdBatterySensor, self).__init__(name, address)
        self._icon = "mdi:battery"
        self._name_suffix = "battery level (%)"
        self._last_battery_level = 0
        self._attributes = {}

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._last_battery_level

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        j = 0
        loop = 3
        battery_level = None
        while j < loop:
            try:
                self._miband.connect()
                self._miband.resolve_service()
                battery_level = self._miband.battery_level()
                break
            except (GATTException, BTIOException) as err:
                _LOGGER.error(err)
                time.sleep(10)
                j = j + 1
        if battery_level:
            self._last_battery_level = battery_level
            self._state = battery_level
            self._last_updated = datetime.now()
            msg = "Last Battery Level {} % at {}".format(self._last_battery_level, self._last_updated)
            _LOGGER.debug(msg)
