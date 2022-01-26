#!/usr/bin/env python3
import logging
import time
from datetime import datetime, timedelta
from threading import Event, Thread
from decorator import decorator
import voluptuous
from gattlib import GATTRequester
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
    device = MiBand(address)
    dev = []
    dev.append(MiBabdBatterySensor(name, device))
    dev.append(MiBabdStepsSensor(name, device))
    dev.append(MiBabdDistanceSensor(name, device))
    dev.append(MiBabdCaloriesSensor(name, device))
    add_devices(dev, True)


class Requester(GATTRequester):
    def __init__(self, wakeup, address, do_connect, device):
        super(Requester, self).__init__(address, do_connect)
        # band device
        self.device = device
        self.wakeup = wakeup

    def on_notification(self, handle, data):
        # self.device.activity_value_handle:
        if handle == 71:
            last_update = time.time()
            steps = int.from_bytes(data[4:8], byteorder='little')
            distance = int.from_bytes(data[8:12], byteorder='little')
            calories = int.from_bytes(data[12:], byteorder='little')
            self.device.update_activity(last_update ,steps, distance, calories)
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
        self.state = {}
        self.fetching_data = False

    def connect(self):
        if not self.is_connected():
            self.requester.connect(True)

    def wait_notification(self):
        self.received.wait(3)

    def resolve_service(self):
        self.primary = self.requester.discover_primary()
        self.characteristic = self.requester.discover_characteristics()
        self.descriptors = self.requester.discover_descriptors()
        self.activity_handle = self.find_char_handle(self.ACTIVITY_UUID)
        self.activity_value_handle = self.activity_handle + 1
        self.activity_notify_handle = self.activity_handle + 2

    def find_char_handle(self, uuid):
        for char in self.characteristic:
            if uuid == char['uuid']:
                return char['handle']
        return None

    def is_connected(self):
        return self.requester.is_connected()

    def disconnect(self):
        if self.requester.is_connected():
            self.requester.disconnect()

    def device_information(self):
        device_name = self.requester.read_by_uuid(self.DEVICE_NAME_UUID)[0]
        serial_num = self.requester.read_by_uuid(self.SERIAL_NUMBER_UUID)[0]
        hardware_rev = self.requester.read_by_uuid(self.HARDWARE_REVISION_UUID)[0]
        software_rev = self.requester.read_by_uuid(self.SOFTWARE_REVISION_UUID)[0]

    def activity_notifications(self, enabled=True):
        self.requester.enable_notifications(self.activity_notify_handle, enabled, False)

    def battery_level(self):
        data = self.requester.read_by_uuid(self.BATTERY_SERVICE_UUID)[0]
        val = int.from_bytes(data, byteorder='little')
        return val

    def update_battery_level(self):
        battery_level = self.battery_level()
        last_updated = time.time()
        self.state["battery_level"] = {
            "last_update": last_updated,
            "value": battery_level}

    def update_activity(self, last_update ,steps, distance, calories):
        self.state["activity"] = {
            "last_update": last_update,
            "steps": steps,
            "distance": distance,
            "calories": calories}

class MiBabdSensor(entity.Entity):
    def __init__(self, name, device):
        self._name = name
        self._device = device
        self._icon = ICON
        self._name_suffix = "Mi Smart Band"
        self._state = const.STATE_UNKNOWN
        self._last_updated = const.STATE_UNKNOWN
        self._attributes = {}

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
    def name_suffix(self):
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
    def __init__(self, name, device):
        super(MiBabdBatterySensor, self).__init__(name, device)
        self._icon = "mdi:battery"
        self._name_suffix = "Battery Level (%)"
        self._attributes = {}
        # this may cause system not up....
        #self._update_data(False)

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "%"

    @decorator
    def _run_as_thread(fn, *args, **kwargs):
        Thread(target=fn, args=args, kwargs=kwargs).start()

    @_run_as_thread
    def _update_data(self, wait_notify=True):
        j = 0
        loop = 10
        while j < loop:
            try:
                err_occur = False
                self._device.connect()
                time.sleep(1)
                self._device.update_battery_level()
                #time.sleep(1)
                #self._device.resolve_service()
                #time.sleep(1)
                #self._device.activity_notifications()
                if not wait_notify:
                    time.sleep(1)
                    self._device.disconnect()
                    break
                for i in range(20):
                    time.sleep(1)
                    if not self._device.is_connected():
                        err_occur = True
                        break
                if err_occur:
                    time.sleep(6)
                    j = j + 1
                else:
                    time.sleep(1)
                    self._device.disconnect()
                    break
            except Exception as err:
                time.sleep(3)
                j = j + 1
        self._fetch_data()

    def _fetch_data(self):
        self._last_updated = self._device.state.get(
            "battery_level", {}).get("last_update", const.STATE_UNKNOWN)
        self._state = self._device.state.get(
            "battery_level", {}).get("value", const.STATE_UNKNOWN)

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._update_data()

class MiBabdStepsSensor(MiBabdSensor):
    def __init__(self, name, device):
        super(MiBabdStepsSensor, self).__init__(name, device)
        self._icon = "mdi:walk"
        self._name_suffix = "Steps"
        self._attributes = {}

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "steps"

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._last_updated = self._device.state.get(
            "activity", {}).get("last_update", const.STATE_UNKNOWN)
        self._state = self._device.state.get(
            "activity", {}).get("steps", const.STATE_UNKNOWN)


class MiBabdDistanceSensor(MiBabdSensor):
    def __init__(self, name, device):
        super(MiBabdDistanceSensor, self).__init__(name, device)
        self._icon = "mdi:walk"
        self._name_suffix = "Distance"
        self._attributes = {}

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "m"

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._last_updated = self._device.state.get(
            "activity", {}).get("last_update", const.STATE_UNKNOWN)
        self._state = self._device.state.get(
            "activity", {}).get("distance", const.STATE_UNKNOWN)


class MiBabdCaloriesSensor(MiBabdSensor):
    def __init__(self, name, device):
        super(MiBabdCaloriesSensor, self).__init__(name, device)
        self._icon = "mdi:food"
        self._name_suffix = "Calories"
        self._attributes = {}

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "cal"

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._last_updated = self._device.state.get(
            "activity", {}).get("last_update", const.STATE_UNKNOWN)
        self._state = self._device.state.get(
            "activity", {}).get("calories", const.STATE_UNKNOWN)
