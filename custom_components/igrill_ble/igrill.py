from builtins import range
from builtins import object
import logging
from collections.abc import Callable
from typing import Optional, Union

from bleak import BleakClient

from bleak_retry_connector import (
    BLEDevice,
    establish_connection,
)

from homeassistant.components.bluetooth.models import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from .const import SensorType
import asyncio
from bluetooth_sensor_state_data import BluetoothData
from sensor_state_data import (
    SensorDeviceClass,
    SensorLibrary,
    SensorUpdate,
    Units,
)
from sensor_state_data.description import BaseSensorDescription

_LOGGER = logging.getLogger(__name__)
CONNECT_LOCK = asyncio.Lock()


class UUIDS(object):
    FIRMWARE_VERSION = "64ac0001-4a4b-4b58-9f37-94d3c52ffdf7"
    HARDWARE_REVISION = "00002a27-0000-1000-8000-00805f9b34fb"
    MANUFACTURER_NAME = "00002a29-0000-1000-8000-00805f9b34fb"

    BATTERY_LEVEL = "00002A19-0000-1000-8000-00805F9B34FB"

    APP_CHALLENGE = "64AC0002-4A4B-4B58-9F37-94D3C52FFDF7"
    DEVICE_CHALLENGE = "64AC0003-4A4B-4B58-9F37-94D3C52FFDF7"
    DEVICE_RESPONSE = "64AC0004-4A4B-4B58-9F37-94D3C52FFDF7"

    CONFIG = "06ef0002-2e06-4b79-9e33-fce2c42805ec"
    PROBE1_TEMPERATURE = "06ef0002-2e06-4b79-9e33-fce2c42805ec"
    PROBE1_THRESHOLD = "06ef0003-2e06-4b79-9e33-fce2c42805ec"
    PROBE2_TEMPERATURE = "06ef0004-2e06-4b79-9e33-fce2c42805ec"
    PROBE2_THRESHOLD = "06ef0005-2e06-4b79-9e33-fce2c42805ec"
    PROBE3_TEMPERATURE = "06ef0006-2e06-4b79-9e33-fce2c42805ec"
    PROBE3_THRESHOLD = "06ef0007-2e06-4b79-9e33-fce2c42805ec"
    PROBE4_TEMPERATURE = "06ef0008-2e06-4b79-9e33-fce2c42805ec"
    PROBE4_THRESHOLD = "06ef0009-2e06-4b79-9e33-fce2c42805ec"
    HEATING_ELEMENTS = "6c91000a-58dc-41c7-943f-518b278ceaaa"
    AMBIENT_TEMPERATURE = "06EF000A-2E06-4B79-9E33-FCE2C42805EC"
    AMBIENT_TEMP_PULSE = "6C910001-58DC-41C7-943F-518B278CEAAA"
    AMBIENT_THRESHOLD = "06EF000B-2E06-4B79-9E33-FCE2C42805EC"
    PROPANE_LEVEL = "F5D40001-3548-4C22-9947-F3673FCE3CD9"
    MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
    SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
    LED_KNOB_TOGGLE = "EAEF0001-3909-454C-9D7E-E68CBA24A9B8"


class IDevicePeripheral(BluetoothData):
    def __init__(
        self,
        name,
        num_probes,
        has_battery=True,
        has_heating_element=False,
        has_propane=False,
        has_led_knob_light=False,
    ):
        """
        Connects to the device given by address performing necessary authentication
        """
        super().__init__()
        self.name = name
        self.has_battery = has_battery
        self.has_propane = has_propane
        self.has_heating_element = has_heating_element
        self.has_led_knob_light = has_led_knob_light
        self.has_ambient_temp = False
        self.num_probes = num_probes
        self.temp_chars = {}
        self.temp_threshold_chars = {}
        self.connected = False
        self.retrieved_device_info = False
        self.is_celsius = False
        self.client = None
        self._listeners = []
        self.data = {}
        self.bt_name = None
        self.address = None
        self.entity_data = {}
        self.closed = False

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = getattr(UUIDS, temp_char_name)
            self.temp_chars[temp_char] = probe_num
            temp_threshold_name = "PROBE{}_THRESHOLD".format(probe_num)
            temp_char = getattr(UUIDS, temp_threshold_name)
            self.temp_threshold_chars[probe_num] = temp_char

    @callback
    def async_add_listener(
        self,
        update_callback: Callable[[SensorUpdate], None],
    ) -> Callable[[], None]:
        """Listen for all updates."""

        @callback
        def remove_listener() -> None:
            """Remove update listener."""
            self._listeners.remove(update_callback)

        self._listeners.append(update_callback)
        return remove_listener

    async def set_led_state(self, ble_device: BLEDevice):
        self.client = await establish_connection(
            BleakClient, ble_device, ble_device.address
        )
        if self.connected and self.has_led_knob_light:
            await self.client.write_gatt_char(UUIDS.LED_KNOB_TOGGLE, [1])

    def _on_disconnect(self, device):
        self.connected = False
        self.client = None
        self.update_listeners()

    def update_listeners(self):
        data = self._finish_update()
        for listener in self._listeners:
            listener(data)

    def update_temp_sensor(self, payload, name):
        temp = payload[0] + (payload[1] * 256)
        temp = float(temp) if float(temp) != 63536.0 else 0
        temp_unit = SensorLibrary.TEMPERATURE__CELSIUS
        self.update_predefined_sensor(temp_unit, temp, name)
        self.update_listeners()

    def update_heating_sensor(self, payload):
        payload = [float(x) for x in payload.decode("utf-8").split()]
        self.update_predefined_sensor(
            SensorLibrary.TEMPERATURE__CELSIUS,
            payload[0],
            "heating_element_left_actual",
        )
        self.update_predefined_sensor(
            SensorLibrary.TEMPERATURE__CELSIUS,
            payload[1],
            "heating_element_right_actual",
        )
        self.update_predefined_sensor(
            SensorLibrary.TEMPERATURE__CELSIUS,
            payload[2],
            "heating_element_left_setpoint",
        )
        self.update_predefined_sensor(
            SensorLibrary.TEMPERATURE__CELSIUS,
            payload[3],
            "heating_element_right_setpoint",
        )
        self.update_listeners()

    def update_propane_sensor(self, payload):
        val = float(payload[0]) * 25
        self.update_predefined_sensor(
            BaseSensorDescription(
                device_class=SensorDeviceClass.GAS,
                native_unit_of_measurement=Units.PERCENTAGE,
            ),
            val,
            "propane_percentage",
        )
        self.update_listeners()

    def update_battery_sensor(self, payload):
        self.update_predefined_sensor(SensorLibrary.BATTERY__PERCENTAGE, payload[0])
        self.update_listeners()

    async def close(self):
        self.closed = True
        if self.connected:
            await self.client.disconnect()

    def get_data(self, key: PassiveBluetoothEntityKey):
        return self.entity_data[key].native_value

    async def async_init(self, ble_device: BLEDevice) -> SensorUpdate:
        """
        Connect to the igrill, receive initial data and then set up listeners to update info async.
        """
        try:
            self.bt_name = ble_device.name
            self.address = ble_device.address
            if not self.connected and not self.closed:
                self.connected = True
                self.client = await establish_connection(
                    BleakClient, ble_device, ble_device.address
                )
                self.client.set_disconnected_callback(
                    lambda device: self._on_disconnect(device)
                )
                await self.client.pair(protection_level=1)

                # send app challenge (16 bytes) (must be wrapped in a bytearray)
                challenge = bytes(b"\0" * 16)
                await self.client.write_gatt_char(UUIDS.APP_CHALLENGE, challenge)

                # Normally we'd have to perform some crypto operations:
                #     Write a challenge (in this case 16 bytes of 0)
                #     Read the value
                #     Decrypt w/ the key
                #     Check the first 8 bytes match our challenge
                #     Set the first 8 bytes 0
                #     Encrypt with the key
                #     Send back the new value
                # But wait!  Our first 8 bytes are already 0.  That means we don't need the key.
                # We just hand back the same encrypted value we get and we're good.
                encrypted_device_challenge = await self.client.read_gatt_char(
                    UUIDS.DEVICE_CHALLENGE
                )
                await self.client.write_gatt_char(
                    UUIDS.DEVICE_RESPONSE, encrypted_device_challenge
                )

                if not self.retrieved_device_info:
                    self.retrieved_device_info = True
                    self.set_device_manufacturer("Weber")
                    self.set_device_type(self.name)
                    payload = await self.client.read_gatt_char(UUIDS.FIRMWARE_VERSION)
                    self.set_device_sw_version(payload.rstrip(b"\x00").decode("utf-8"))
                char_ids = {}
                services = await self.client.get_services()
                for char, probe_id in self.temp_chars.items():
                    char_ids[services.get_characteristic(char).handle] = probe_id
                    await self.client.start_notify(
                        char,
                        lambda handle, payload: self.update_temp_sensor(
                            payload, f"probe_{char_ids[handle]}"
                        ),
                    )
                    self.update_temp_sensor(
                        await self.client.read_gatt_char(char), f"probe_{probe_id}"
                    )

                if (await self.client.get_services()).get_characteristic(
                    UUIDS.AMBIENT_TEMPERATURE
                ):
                    self.has_ambient_temp = True
                    await self.client.start_notify(
                        UUIDS.AMBIENT_TEMPERATURE,
                        lambda handle, payload: self.update_temp_sensor(
                            payload, "ambient_temp"
                        ),
                    )
                    self.update_temp_sensor(
                        await self.client.read_gatt_char(UUIDS.AMBIENT_TEMPERATURE),
                        "ambient_temp",
                    )

                if self.has_heating_element:
                    await self.client.start_notify(
                        UUIDS.HEATING_ELEMENTS,
                        lambda handle, payload: self.update_heating_sensor(payload),
                    )
                    await self.update_heating_sensor(
                        self.client.read_gatt_char(UUIDS.HEATING_ELEMENTS),
                    )
                if self.has_battery:
                    await self.client.start_notify(
                        UUIDS.BATTERY_LEVEL,
                        lambda handle, payload: self.update_battery_sensor(payload),
                    )
                    payload = await self.client.read_gatt_char(UUIDS.BATTERY_LEVEL)
                    self.update_battery_sensor(payload)
                if self.has_propane:
                    await self.client.start_notify(
                        UUIDS.PROPANE_LEVEL,
                        lambda handle, payload: self.update_propane_sensor(payload),
                    )
                    self.update_propane_sensor(
                        await self.client.read_gatt_char(UUIDS.PROPANE_LEVEL),
                    )
        except Exception:
            self.connected = False
            raise
        return self._finish_update()


class KitchenThermometerPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Kitchen Thermometer
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "Kitchen Thermometer", 2)


class KitchenThermometerMiniPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Kitchen Thermometer Mini
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "Kitchen Thermometer Mini", 1)


class IGrillMini2Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill Mini 2
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "iGrill Mini 2", 1)


class IGrillMiniPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill Mini
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "iGrill Mini", 1)


class IGrillV22Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v2 2
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "iGrill V2 2", 4)


class IGrillV2Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v2
    """

    def __init__(self):
        IDevicePeripheral.__init__(self, "iGrill V2", 4)


class IGrillV3Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v3
    """

    def __init__(self):
        IDevicePeripheral.__init__(
            self, "iGrill V3", 4, has_led_knob_light=True, has_propane=True
        )


class Pulse1000Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Pulse 1000
    """

    def __init__(self):
        IDevicePeripheral.__init__(
            self, "Pulse 1000", 2, has_heating_element=True, has_battery=False
        )


class Pulse2000Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Pulse 2000
    """

    def __init__(self):
        IDevicePeripheral.__init__(
            self, "Pulse 2000", 4, has_heating_element=True, has_battery=False
        )


DEVICE_TYPES = {
    SensorType.IGRILL_MINI.value: IGrillMiniPeripheral,
    SensorType.IGRILL_MINI_2.value: IGrillMini2Peripheral,
    SensorType.IGRILL_V2.value: IGrillV2Peripheral,
    SensorType.IGRILL_V2_2.value: IGrillV22Peripheral,
    SensorType.IGRILL_V3.value: IGrillV3Peripheral,
    SensorType.PULSE_1000.value: Pulse1000Peripheral,
    SensorType.PULSE_2000.value: Pulse2000Peripheral,
    SensorType.KITCHEN_THERMOMETER.value: KitchenThermometerPeripheral,
    SensorType.KITCHEN_THERMOMETER_MINI.value: KitchenThermometerMiniPeripheral,
}
