from builtins import range
from builtins import object
import logging

import asyncio
from bleak import BleakClient

_LOGGER = logging.getLogger(__name__)

class UUIDS(object):
    FIRMWARE_VERSION   = "64ac0001-4a4b-4b58-9f37-94d3c52ffdf7"

    BATTERY_LEVEL      = "00002A19-0000-1000-8000-00805F9B34FB"

    APP_CHALLENGE      = "64AC0002-4A4B-4B58-9F37-94D3C52FFDF7"
    DEVICE_CHALLENGE   = "64AC0003-4A4B-4B58-9F37-94D3C52FFDF7"
    DEVICE_RESPONSE    = "64AC0004-4A4B-4B58-9F37-94D3C52FFDF7"

    CONFIG             = "06ef0002-2e06-4b79-9e33-fce2c42805ec"
    PROBE1_TEMPERATURE = "06ef0002-2e06-4b79-9e33-fce2c42805ec"
    PROBE1_THRESHOLD   = "06ef0003-2e06-4b79-9e33-fce2c42805ec"
    PROBE2_TEMPERATURE = "06ef0004-2e06-4b79-9e33-fce2c42805ec"
    PROBE2_THRESHOLD   = "06ef0005-2e06-4b79-9e33-fce2c42805ec"
    PROBE3_TEMPERATURE = "06ef0006-2e06-4b79-9e33-fce2c42805ec"
    PROBE3_THRESHOLD   = "06ef0007-2e06-4b79-9e33-fce2c42805ec"
    PROBE4_TEMPERATURE = "06ef0008-2e06-4b79-9e33-fce2c42805ec"
    PROBE4_THRESHOLD   = "06ef0009-2e06-4b79-9e33-fce2c42805ec"
    HEATING_ELEMENTS   = "6c91000a-58dc-41c7-943f-518b278ceaaa"

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
        self.heating_ele_val = 0
        self.temps = {1: 0, 2: 0, 3: 0, 4: 0}

    async def authenticate(self, client):
        """
        Performs iDevices challenge/response handshake. Returns if handshake succeeded
        Works for all devices using this handshake, no key required
        (copied from https://github.com/kins-dev/igrill-smoker, thanks for the tip!)
        """
        _LOGGER.debug("Setting security...")
        await client.pair(protection_level=1)
        _LOGGER.debug("Grabbing characteristics...")

        self.temp_chars = {}

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = getattr(UUIDS, temp_char_name)
            self.temp_chars[probe_num] = temp_char
            _LOGGER.debug("Added probe with index {0}, name {1}, and UUID {2}".format(probe_num, temp_char_name, temp_char))
        _LOGGER.debug("Authenticating...")

        challenge = bytes(b'\0' * 16)
        _LOGGER.debug("Sending key of all 0's")
        await client.write_gatt_char(UUIDS.APP_CHALLENGE, challenge)
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
        encrypted_device_challenge = await client.read_gatt_char(UUIDS.DEVICE_CHALLENGE)
        await client.write_gatt_char(UUIDS.DEVICE_RESPONSE, encrypted_device_challenge)

        _LOGGER.debug("Authenticated")
        return True

    async def update(self):
        async with BleakClient(self.address) as client:
            if await self.authenticate(client):
                self.heating_ele_val = (await client.read_gatt_char(UUIDS.HEATING_ELEMENTS)) if self.has_heating_element else None
                for probe_num, temp_char in list(self.temp_chars.items()):
                    temp = (await client.read_gatt_char(temp_char))
                    temp = temp[1] * 256 + temp[0]
                    self.temps[probe_num] = float(temp) if float(temp) != 63536.0 else 0
                battery = (await client.read_gatt_char(UUIDS.BATTERY_LEVEL))[0]
                return float(battery) if self.has_battery else None
            else:
                self.heating_ele_val = 0
                self.temps = {1: 0, 2: 0, 3: 0, 4: 0}
                self.battery = 0


    def read_battery(self):
        return self.battery

    def read_heating_elements(self):
        return self.heating_ele_val

    def read_temperature(self):
        return self.temps


class IGrillMiniPeripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill Mini
    """

    def __init__(self, address, name='IGrill Mini', num_probes=1):
        IDevicePeripheral.__init__(self, address, name, num_probes)


class IGrillV2Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v2
    """

    def __init__(self, address, name='IGrill V2', num_probes=4):
        IDevicePeripheral.__init__(self, address, name, num_probes)


class IGrillV3Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the iGrill v3
    """

    def __init__(self, address, name='IGrill V3', num_probes=4):
        IDevicePeripheral.__init__(self, address, name, num_probes)


class Pulse2000Peripheral(IDevicePeripheral):
    """
    Specialization of iDevice peripheral for the Weber Pulse 2000
    """

    def __init__(self, address, name='Pulse 2000', num_probes=4):
        IDevicePeripheral.__init__(self, address, name, num_probes, has_heating_element=True)
