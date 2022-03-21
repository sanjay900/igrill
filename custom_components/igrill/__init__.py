"""The igrill component."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    Platform,
    CONF_MAC
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .igrill import IDevicePeripheral
from .const import DEVICE_TYPES, DOMAIN, LOGGER, SERVICE_IGRILL, SCAN_INTERVAL, CONF_SENSORTYPE

# List of platforms to support. There should be a matching .py file for each,
# eg <cover.py> and <sensor.py>
PLATFORMS: list[str] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    sensortype = entry.data(CONF_SENSORTYPE)
    mac = entry.data(CONF_MAC)
    sensor = DEVICE_TYPES[sensortype](mac)  

    igrill_update: DataUpdateCoordinator[IDevicePeripheral] = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{DOMAIN}_{SERVICE_IGRILL}",
        update_interval=SCAN_INTERVAL,
        update_method=sensor.update,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = igrill_update
    await igrill_update.async_config_entry_first_refresh()

    # It's done by calling the `async_setup_entry` function in each platform module.
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    hass.data[DOMAIN][entry.entry_id].close()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
