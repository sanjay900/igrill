"""Config flow for Xiaomi Bluetooth integration."""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import onboarding
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import SensorType, DOMAIN, CONF_SENSORTYPE

# How long to wait for additional advertisement packets if we don't have the right ones
ADDITIONAL_DISCOVERY_TIMEOUT = 60

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""

    title: str
    discovery_info: BluetoothServiceInfo
    device: str


class IGrillFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Xiaomi Bluetooth."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfo | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    def get_device_type(self, name: str) -> str | None:
        """Resolve a bluetooth device name into a grill sensor type"""
        for sensor_type in SensorType:
            if name.lower().startswith(sensor_type.value):
                return sensor_type
        return None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        found_type = self.get_device_type(discovery_info.name)
        if not found_type:
            return self.async_abort(reason="not_supported")

        title = discovery_info.name
        self.context["title_placeholders"] = {"name": title}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None or not onboarding.async_is_onboarded(self.hass):
            return self._async_get_or_create_entry()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_confirm_slow(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ack that device is slow."""
        if user_input is not None:
            return self._async_get_or_create_entry()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm_slow",
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery = self._discovered_devices[address]

            self.context["title_placeholders"] = {"name": discovery.title}

            return self._async_get_or_create_entry()

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            dev_type = self.get_device_type(discovery_info.name)
            if dev_type:
                self._discovered_devices[address] = Discovery(
                    title=discovery_info.name,
                    discovery_info=discovery_info,
                    device=dev_type,
                )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        titles = {
            address: discovery.title
            for (address, discovery) in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(titles)}),
        )

    def _async_get_or_create_entry(self):
        data = {
            CONF_SENSORTYPE: self.get_device_type(
                self.context["title_placeholders"]["name"]
            ).value
        }

        return self.async_create_entry(
            title=self.context["title_placeholders"]["name"],
            data=data,
        )
