from builtins import range
from builtins import object
import logging
from typing import Optional


from bleak import BleakClient
from bleak_retry_connector import (
    BLEDevice,
    establish_connection,
)
from home_assistant_bluetooth import BluetoothServiceInfo
from .const import DEVICE_TIMEOUT, SensorType
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
    SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"


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
        self.available = False
        self.retrieved_device_info = False

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = getattr(UUIDS, temp_char_name)
            self.temp_chars[probe_num] = temp_char

    def poll_needed(
        self, service_info: BluetoothServiceInfo, last_poll: Optional[float]
    ) -> bool:
        return not last_poll or last_poll > DEVICE_TIMEOUT

    async def async_poll(self, ble_device: BLEDevice) -> SensorUpdate:
        """
        Poll the device to retrieve any values we can't get from passive listening.
        """
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        try:
            await client.pair(protection_level=1)

            # send app challenge (16 bytes) (must be wrapped in a bytearray)
            challenge = bytes(b"\0" * 16)
            await client.write_gatt_char(UUIDS.APP_CHALLENGE, challenge)

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
            encrypted_device_challenge = await client.read_gatt_char(
                UUIDS.DEVICE_CHALLENGE
            )
            await client.write_gatt_char(
                UUIDS.DEVICE_RESPONSE, encrypted_device_challenge
            )

            if not self.retrieved_device_info:
                self.retrieved_device_info = True
                self.set_device_manufacturer("Weber")
                self.set_device_type(self.name)
                payload = await client.read_gatt_char(UUIDS.FIRMWARE_VERSION)
                self.set_device_sw_version(payload.rstrip(b"\x00").decode("utf-8"))
                if (await client.get_services()).get_characteristic(
                    UUIDS.AMBIENT_TEMPERATURE
                ):
                    self.has_ambient_temp = True

            for probe_num, char in self.temp_chars.items():
                payload = await client.read_gatt_char(char)
                temp = payload[0] + (payload[1] * 256)
                temp = float(temp) if float(temp) != 63536.0 else 0
                self.update_predefined_sensor(
                    SensorLibrary.TEMPERATURE__CELSIUS, temp, f"probe_{probe_num}"
                )
            if self.has_ambient_temp:
                payload = await client.read_gatt_char(UUIDS.AMBIENT_TEMPERATURE)
                self.update_predefined_sensor(
                    SensorLibrary.TEMPERATURE__CELSIUS, payload[0], "ambient_temp"
                )
            if self.has_heating_element:
                payload = await client.read_gatt_char(UUIDS.HEATING_ELEMENTS)
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
            if self.has_battery:
                payload = await client.read_gatt_char(UUIDS.BATTERY_LEVEL)
                self.update_predefined_sensor(
                    SensorLibrary.BATTERY__PERCENTAGE, payload[0]
                )
            if self.has_propane:
                payload = await client.read_gatt_char(UUIDS.BATTERY_LEVEL)
                val = float(payload[0]) * 25
                self.update_predefined_sensor(
                    BaseSensorDescription(
                        device_class=SensorDeviceClass.GAS,
                        native_unit_of_measurement=Units.PERCENTAGE,
                    ),
                    val,
                    "propane_percentage",
                )

        finally:
            await client.disconnect()

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
