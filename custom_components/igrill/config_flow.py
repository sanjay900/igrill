"""Config flow to configure the igrill integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

import asyncio

from .igrill import IDevicePeripheral

from bleak import BleakError

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import (
    CONF_NAME,
    CONF_MAC,
)
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_SENSORTYPE, DEVICE_TYPES


class igrillFlowHandler(ConfigFlow, domain=DOMAIN):
    """Config flow for igrill."""

    VERSION = 1

    entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            try:
                sensortype = user_input[CONF_SENSORTYPE]
                mac = user_input[CONF_MAC]
                device = DEVICE_TYPES[sensortype](mac)
                await asyncio.get_event_loop().run_in_executor(None, IDevicePeripheral.read_battery, device)
            except BleakError as e:
                print(e)
                errors["base"] = " ".join(str(r) for r in e.args)
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_SENSORTYPE: user_input[CONF_SENSORTYPE],
                        CONF_MAC: user_input[CONF_MAC],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_MAC): str,
                    vol.Required(CONF_SENSORTYPE): ["igrill_mini","igrill_v2","igrill_v3","pulse_2000"]
                }
            ),
            errors=errors,
        )
