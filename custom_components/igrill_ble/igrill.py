from builtins import range
from builtins import object
import logging
import time
import threading
from typing import Optional


from bleak import BleakError, BleakScanner, BleakClient
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BLEDevice,
    establish_connection,
)
from homeassistant.components.bluetooth.models import BluetoothServiceInfoBleak
from homeassistant.helpers import device_registry as dr
from home_assistant_bluetooth import BluetoothServiceInfo
from .const import DEVICE_TIMEOUT, SensorType
import asyncio
import random
from queue import Queue
from bluetooth_sensor_state_data import BluetoothData
from sensor_state_data import (
    BinarySensorDeviceClass,
    DeviceClass,
    SensorLibrary,
    SensorUpdate,
    Units,
)

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
    SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"


class IDevicePeripheral(BluetoothData):
    has_battery = None
    has_heating_element = None
    authenticated = False

    def __init__(
        self,
        name,
        num_probes,
        has_battery=True,
        has_heating_element=False,
    ):
        """
        Connects to the device given by address performing necessary authentication
        """
        super().__init__()
        self.name = name
        self.has_battery = has_battery
        self.has_heating_element = has_heating_element
        self.num_probes = num_probes
        self.heatingEleVal = 0
        self.temps = {1: 0, 2: 0, 3: 0, 4: 0}
        self.temp_chars = {}
        self.battery = 0
        self.available = False
        self.retrieved_device_info = False

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = getattr(UUIDS, temp_char_name)
            self.temp_chars[probe_num] = temp_char

    def poll_needed(
        self, service_info: BluetoothServiceInfo, last_poll: Optional[float]
    ) -> bool:
        _LOGGER.info(last_poll)
        return not last_poll or last_poll > DEVICE_TIMEOUT

    async def async_poll(self, ble_device: BLEDevice) -> SensorUpdate:
        """
        Poll the device to retrieve any values we can't get from passive listening.
        """
        _LOGGER.info("Poll!")
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
            for probe_num, char in self.temp_chars.items():
                payload = await client.read_gatt_char(char)
                temp = payload[0] + (payload[1] * 256)
                temp = float(temp) if float(temp) != 63536.0 else 0
                self.update_predefined_sensor(
                    SensorLibrary.TEMPERATURE__CELSIUS, temp, f"probe_{probe_num}"
                )
            if self.has_heating_element:
                payload = await client.read_gatt_char(UUIDS.HEATING_ELEMENTS)
                self.update_predefined_sensor(
                    SensorLibrary.TEMPERATURE__CELSIUS, payload[0], "heating_element"
                )
            if self.has_battery:
                payload = await client.read_gatt_char(UUIDS.BATTERY_LEVEL)
                self.update_predefined_sensor(
                    SensorLibrary.BATTERY__PERCENTAGE, payload[0]
                )
            if not self.retrieved_device_info:
                self.retrieved_device_info = True
                self.set_device_manufacturer("Weber")
                self.set_device_type(self.name)
                payload = await client.read_gatt_char(UUIDS.FIRMWARE_VERSION)
                self.set_device_sw_version(payload.rstrip(b"\x00").decode("utf-8"))

        finally:
            await client.disconnect()

        return self._finish_update()


class IGrillMiniPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill Mini
    """

    def __init__(self, name="iGrill Mini", num_probes=1):
        IDevicePeripheral.__init__(self, name, num_probes)


class IGrillV2Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v2
    """

    def __init__(self, name="iGrill V2", num_probes=4):
        IDevicePeripheral.__init__(self, name, num_probes)


class IGrillV3Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v3
    """

    def __init__(self, name="iGrill V3", num_probes=4):
        IDevicePeripheral.__init__(self, name, num_probes)


class Pulse2000Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Pulse 2000
    """

    def __init__(self, name="Pulse 2000", num_probes=4):
        IDevicePeripheral.__init__(self, name, num_probes, has_heating_element=True)


DEVICE_TYPES = {
    SensorType.IGRILL_MINI.value: IGrillMiniPeripheral,
    SensorType.IGRILL_V2.value: IGrillV2Peripheral,
    SensorType.IGRILL_V3.value: IGrillV3Peripheral,
    SensorType.PULSE_2000.value: Pulse2000Peripheral,
}
