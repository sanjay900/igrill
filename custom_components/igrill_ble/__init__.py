"""The igrill component."""
from __future__ import annotations
import logging
from homeassistant.components import bluetooth

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import Platform

from .igrill import DEVICE_TYPES
from .const import (
    DOMAIN,
    CONF_SENSORTYPE,
)
from homeassistant.components.bluetooth.match import (
    ADDRESS,
    BluetoothCallbackMatcher,
)

PLATFORMS: list[str] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Weber iGrill device from a config entry."""
    address = entry.unique_id
    assert address is not None
    sensor_type = entry.data[CONF_SENSORTYPE]
    data = DEVICE_TYPES[sensor_type]()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update from a ble callback."""
        hass.async_create_task(data.async_poll(service_info.device))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            BluetoothCallbackMatcher({ADDRESS: address}),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )  # only start after all platforms have had a chance to subscribe
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.data[DOMAIN][entry.entry_id].close()
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
