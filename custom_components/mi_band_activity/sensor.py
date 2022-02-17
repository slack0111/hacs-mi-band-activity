#!/usr/bin/env python3
import asyncio
import logging
import time
from datetime import datetime, timedelta
from threading import Event, Thread
from decorator import decorator
import voluptuous
from gattlib import GATTRequester, GATTResponse
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
        if handle == 71 and not self.device.fetching_data:
            last_update = time.time()
            steps = int.from_bytes(data[4:8], byteorder='little')
            distance = int.from_bytes(data[8:12], byteorder='little')
            calories = int.from_bytes(data[12:], byteorder='little')
            self.device.update_activity(last_update ,steps, distance, calories)
        self.wakeup.set()


class MiBand(object):
    BATTERY_SERVICE_UUID = '00002a19-0000-1000-8000-00805f9b34fb'

    def __init__(self, address):
        self._received = Event()
        self._requester = Requester(self._received, address, False, self)
        self._response = GATTResponse()
        self._address = address
        self._battery_level = 0
        self._fetching_data = False
        self._state = {}

    @property
    def battery_level(self):
        return self._battery_level

    def connect(self):
        if not self.is_connected():
            try:
                self._requester.connect(True)
            except RuntimeError as err:
                print("[RuntimeError]: {}".format(err))

    async def connect_async(self):
        print(self.connect_async.__name__)
        if not self.is_connected():
            try:
                self._requester.connect(False)
            except RuntimeError as err:
                print("[RuntimeError]: {}".format(err))
        for i in range(90):
            if self.is_connected():
                break
            await asyncio.sleep(0.1)

    def is_connected(self):
        return self._requester.is_connected()

    def disconnect(self):
        if self._requester.is_connected():
            self._requester.disconnect()

    @property
    def fetching_data(self):
        return self._fetching_data

    async def get_battery_level_async(self):
        print(self.get_battery_level_async.__name__)
        for i in range(90):
            if self.is_connected():
                try:
                    data = self._requester.read_by_uuid(self.BATTERY_SERVICE_UUID)[0]
                    self._battery_level = int.from_bytes(data, byteorder='little')
                    self.__update_battery_level()
                    break
                except RuntimeError as err:
                    print("[RuntimeError]: {}".format(err))
            await asyncio.sleep(0.1)

    async def wait_activity_notify(self):
        print(self.wait_activity_notify.__name__)
        for i in range(90):
            if self._fetching_data:
                break
            await asyncio.sleep(0.1)

    @property
    def state(self):
        return self._state

    def __update_battery_level(self):
        battery_level = self._battery_level
        if battery_level == 0:
            return
        last_updated = time.time()
        self.state["battery_level"] = {
            "last_update": last_updated,
            "value": battery_level}
        print(self.state["battery_level"])

    def update_activity(self, last_update ,steps, distance, calories):
        self.state["activity"] = {
            "last_update": last_update,
            "steps": steps,
            "distance": distance,
            "calories": calories}
        print(self.state["activity"])
        self._fetching_data = True

    def reset(self):
        self._fetching_data = False


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

    @property
    def name(self):
        """Returns the name of the sensor."""
        return SENSOR_NAME.format(self._name, self._name_suffix)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return "%"

    async def _update_data(self):
        self._device.reset()
        task1 = asyncio.create_task(self._device.connect_async()) 
        task2 = asyncio.create_task(self._device.get_battery_level_async()) 
        task3 = asyncio.create_task(self._device.wait_activity_notify()) 
        await task1
        await task2
        await task3
        self._device.disconnect()

    def _fetch_data(self):
        self._last_updated = self._device.state.get(
            "battery_level", {}).get("last_update", const.STATE_UNKNOWN)
        self._state = self._device.state.get(
            "battery_level", {}).get("value", const.STATE_UNKNOWN)

    @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        asyncio.run(self._update_data())
        self._fetch_data()

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
