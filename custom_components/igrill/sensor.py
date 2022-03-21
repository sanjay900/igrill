"""Support for displaying collected data over SNMP."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.components.sensor import PLATFORM_SCHEMA,  Entity
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_SENSORTYPE, DOMAIN
)
from .igrill import IDevicePeripheral


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solutions3000 sensors based on a config entry."""
    sensor: IDevicePeripheral = hass.data[DOMAIN][entry.entry_id].data
    sensortype = entry.data(CONF_SENSORTYPE)
    mac = entry.data(CONF_MAC)
    async_add_entities(
        IGrillSensor(
            coordinator=hass.data[DOMAIN][entry.entry_id],
            entry_id=entry.entry_id,
            sensortype=sensortype,
            mac=mac,
            device=sensor,
            probe=probe,
            battery=probe == -1

        )
        for probe in range(-1, sensor.num_probes)
    )


class IGrillSensor(CoordinatorEntity, Entity):
    """Representation of a SNMP sensor."""

    def __init__(self, coordinator: DataUpdateCoordinator, entry_id: str, device: IDevicePeripheral, sensortype, mac, probe, battery):
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)
        if battery:
            self._name = "%s - Battery" % (device.name)
            self._unique_id = "%s_battery" % (mac)
        else:
            self._name = "%s - Probe %d" % (device.name, probe)
            self._unique_id = "%s_probe_%d" % (mac, probe)
        self._state = None
        self._probe = probe
        self._battery = battery
        self._device = device
        self._sensortype = sensortype
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN)},
            manufacturer="Weber",
            model=device.name,
            name=self._name,
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        if self._battery:
            return "%"
        else:
            return "°C"

    async def async_update(self):
        """Get the latest data and updates the states."""
        if self._battery:
            self._state = self._device.read_battery()
        else:
            self._state = self._device.read_temperature()[self._probe]
