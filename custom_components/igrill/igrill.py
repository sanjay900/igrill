from builtins import range
from builtins import object
import logging
import time
import threading


import bleak
from bleak import BleakScanner
import asyncio
import random
from queue import Queue

_LOGGER = logging.getLogger(__name__)
CONNECT_LOCK = asyncio.Lock()
class UUIDS(object):
    FIRMWARE_VERSION   = '64ac0001-4a4b-4b58-9f37-94d3c52ffdf7'

    BATTERY_LEVEL      = '00002A19-0000-1000-8000-00805F9B34FB'

    APP_CHALLENGE      = '64AC0002-4A4B-4B58-9F37-94D3C52FFDF7'
    DEVICE_CHALLENGE   = '64AC0003-4A4B-4B58-9F37-94D3C52FFDF7'
    DEVICE_RESPONSE    = '64AC0004-4A4B-4B58-9F37-94D3C52FFDF7'

    CONFIG             = '06ef0002-2e06-4b79-9e33-fce2c42805ec'
    PROBE1_TEMPERATURE = '06ef0002-2e06-4b79-9e33-fce2c42805ec'
    PROBE1_THRESHOLD   = '06ef0003-2e06-4b79-9e33-fce2c42805ec'
    PROBE2_TEMPERATURE = '06ef0004-2e06-4b79-9e33-fce2c42805ec'
    PROBE2_THRESHOLD   = '06ef0005-2e06-4b79-9e33-fce2c42805ec'
    PROBE3_TEMPERATURE = '06ef0006-2e06-4b79-9e33-fce2c42805ec'
    PROBE3_THRESHOLD   = '06ef0007-2e06-4b79-9e33-fce2c42805ec'
    PROBE4_TEMPERATURE = '06ef0008-2e06-4b79-9e33-fce2c42805ec'
    PROBE4_THRESHOLD   = '06ef0009-2e06-4b79-9e33-fce2c42805ec'
    HEATING_ELEMENTS   = '6c91000a-58dc-41c7-943f-518b278ceaaa'


class IDevicePeripheral():
    encryption_key = None
    has_battery = None
    has_heating_element = None
    authenticated = False

    def __init__(self, address, name, num_probes, has_battery=True, has_heating_element=False):
        """
        Connects to the device given by address performing necessary authentication
        """
        self.name = name
        self.address = address
        self.has_battery = has_battery
        self.has_heating_element = has_heating_element
        self.num_probes = num_probes
        self.heatingEleVal = 0
        self.temps = {1: 0, 2: 0, 3: 0, 4: 0}
        self.temp_chars = {}
        self.battery = 0
        self._device = None
        self.available = False

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = getattr(UUIDS, temp_char_name)
            self.temp_chars[probe_num] = temp_char
            _LOGGER.debug("Added probe with index {0}, name {1}, and UUID {2}".format(probe_num, temp_char_name, temp_char))
    async def _disconnect(self):
        if self._device is not None:
            await self._device.disconnect()
    async def _connect(self) -> bool:
        # Disconnect before connecting
        await self._disconnect()
        async with BleakScanner() as scanner:
            await asyncio.sleep(5.0)
            for d in scanner.discovered_devices:
                if d.address == self.address:
                    _LOGGER.debug("Connecting...")
                    self._device = bleak.BleakClient(self.address)
                    await self._device.connect()
    async def authenticate(self):
        """
        Performs iDevices challenge/response handshake. Returns if handshake succeeded
        Works for all devices using this handshake, no key required
        (copied from https://github.com/kins-dev/igrill-smoker, thanks for the tip!)
        """
        if not self.authenticated:
            await self._connect()
            await self._device.pair(protection_level=1)
            _LOGGER.debug("Authenticating...")

            # send app challenge (16 bytes) (must be wrapped in a bytearray)
            challenge = bytes(b'\0' * 16)
            _LOGGER.debug("Sending key of all 0's")
            await self._device.write_gatt_char(UUIDS.APP_CHALLENGE, challenge)

            """
            Normally we'd have to perform some crypto operations:
                Write a challenge (in this case 16 bytes of 0)
                Read the value
                Decrypt w/ the key
                Check the first 8 bytes match our challenge
                Set the first 8 bytes 0
                Encrypt with the key
                Send back the new value
            But wait!  Our first 8 bytes are already 0.  That means we don't need the key.
            We just hand back the same encrypted value we get and we're good.
            """
            encrypted_device_challenge = await self._device.read_gatt_char(UUIDS.DEVICE_CHALLENGE)
            await self._device.write_gatt_char(UUIDS.DEVICE_RESPONSE, encrypted_device_challenge)

            _LOGGER.debug("Authenticated")
            self.authenticated = True
            return True
        return False
    async def close(self):
        async with CONNECT_LOCK:
            await self._disconnect()
    async def update(self):
        try:
            async with CONNECT_LOCK:
                if not self.authenticated:
                    await self.authenticate()
                if self.authenticated:
                    self.heatingEleVal = bytearray(await self._device.read_gatt_char(UUIDS.HEATING_ELEMENTS)) if self.has_heating_element else 0
                    for probe_num, temp_char in list(self.temp_chars.items()):
                        data = bytearray(await self._device.read_gatt_char(temp_char))
                        temp = data[0] + (data[1] * 256)
                        self.temps[probe_num] = float(temp) if float(temp) != 63536.0 else 0
                    self.battery = float(bytearray(await self._device.read_gatt_char(UUIDS.BATTERY_LEVEL))[0])
        except bleak.BleakError:
            _LOGGER.error("Failed to connect to igrill",
                exc_info=logging.DEBUG >= _LOGGER.root.level)
            self.authenticated = False
        except asyncio.exceptions.TimeoutError:
            self.authenticated = False
        return self

    def read_temperature(self,probe):
        if not self.authenticated: 
            return 0
        return self.temps[probe]

    def read_battery(self):
        if not self.authenticated: 
            return 0
        return self.battery
    def read_heating_elements(self):
        if not self.authenticated: 
            return 0
        return self.heatingEleVal


class IGrillMiniPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill Mini
    """

    def __init__(self, address, name='igrill_mini', num_probes=1):
        _LOGGER.debug("Created new device with name {}".format(name))
        IDevicePeripheral.__init__(self, address, name, num_probes)


class IGrillV2Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v2
    """

    def __init__(self, address, name='igrill_v2', num_probes=4):
        _LOGGER.debug("Created new device with name {}".format(name))
        IDevicePeripheral.__init__(self, address, name, num_probes)


class IGrillV3Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v3
    """

    def __init__(self, address, name='igrill_v3', num_probes=4):
        _LOGGER.debug("Created new device with name {}".format(name))
        IDevicePeripheral.__init__(self, address, name, num_probes)


class Pulse2000Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Pulse 2000
    """

    def __init__(self, address, name='pulse_2000', num_probes=4):
        _LOGGER.debug("Created new device with name {}".format(name))
        IDevicePeripheral.__init__(self, address, name, num_probes, has_heating_element=True)


async def main():
    igrill = IGrillV2Peripheral("70:91:8F:0E:45:9C")
    await igrill.update()
    print(igrill.temps)
    print(igrill.battery)

if __name__ == '__main__':
    asyncio.run(main())