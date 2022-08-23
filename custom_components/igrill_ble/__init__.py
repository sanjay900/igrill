"""The igrill component."""
from __future__ import annotations
import logging
from homeassistant import config_entries
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothProcessorCoordinator,
)
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.components.bluetooth.models import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, CONF_MAC

from .igrill import DEVICE_TYPES
from .const import (
    DOMAIN,
    CONF_SENSORTYPE,
    SensorType,
)

PLATFORMS: list[str] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Weber iGrill device from a config entry."""
    address = entry.unique_id
    assert address is not None
    sensor_type = entry.data[CONF_SENSORTYPE]
    data = DEVICE_TYPES[sensor_type]()

    def _needs_poll(
        service_info: BluetoothServiceInfoBleak, last_poll: float | None
    ) -> bool:
        return data.poll_needed(service_info, last_poll)

    async def _async_poll(service_info: BluetoothServiceInfoBleak):
        # Make sure the device we have is one that we can connect with
        # in case its coming from a passive scanner
        if service_info.connectable:
            connectable_device = service_info.device
        elif device := async_ble_device_from_address(
            hass, service_info.device.address, True
        ):
            connectable_device = device
        else:
            # We have no bluetooth controller that is in range of
            # the device to poll it
            raise RuntimeError(
                f"No connectable device found for {service_info.device.address}"
            )
        return await data.async_poll(connectable_device)

    def _update(service_info):
        return data.update(service_info)

    coordinator = hass.data.setdefault(DOMAIN, {})[
        entry.entry_id
    ] = ActiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=_update,
        needs_poll_method=_needs_poll,
        poll_method=_async_poll,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        coordinator.async_start()
    )  # only start after all platforms have had a chance to subscribe
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
