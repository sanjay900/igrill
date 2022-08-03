"""Config flow to configure the igrill integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

import asyncio

from .igrill import _LOGGER, IDevicePeripheral
from .bt_helpers import (
    DEFAULT_BT_INTERFACE,
    BT_MULTI_SELECT,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.helpers import device_registry, config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_SENSORTYPE, DEVICE_TYPES, SensorType, CONF_BT_INTERFACE


class IGrillFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for igrill."""

    VERSION = 2

    entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            sensortype = user_input[CONF_SENSORTYPE].value
            mac = user_input[CONF_MAC]
            device = DEVICE_TYPES[sensortype](mac)
            await device.update()
            name = device.name
            if not device.authenticated:
                errors["base"] = "not_authenticated"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_SENSORTYPE: user_input[CONF_SENSORTYPE].value,
                        CONF_MAC: user_input[CONF_MAC],
                        CONF_BT_INTERFACE: DEFAULT_BT_INTERFACE
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BT_INTERFACE, default=[DEFAULT_BT_INTERFACE]
                    ): cv.multi_select(BT_MULTI_SELECT),
                    vol.Required(CONF_MAC): str,
                    vol.Required(CONF_SENSORTYPE): vol.Coerce(SensorType),
                }
            ),
            errors=errors,
        )
