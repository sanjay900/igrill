"""The igrill component."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    Platform,
    CONF_MAC
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bt_helpers import DEFAULT_HCI_INTERFACE

from .igrill import IDevicePeripheral
from .const import CONF_BT_INTERFACE, DEVICE_TYPES, DOMAIN, LOGGER, SERVICE_IGRILL, SCAN_INTERVAL, CONF_SENSORTYPE, SensorType

# List of platforms to support. There should be a matching .py file for each,
# eg <cover.py> and <sensor.py>
PLATFORMS: list[str] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    sensortype = entry.data[CONF_SENSORTYPE]
    mac = entry.data[CONF_MAC]
    hci = entry.data[CONF_BT_INTERFACE]
    sensor = DEVICE_TYPES[sensortype](mac, hci)  

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


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:

        new = {**config_entry.data}
        new[CONF_BT_INTERFACE] = DEFAULT_HCI_INTERFACE

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=new)

    LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    await hass.data[DOMAIN][entry.entry_id].data.close()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
