from builtins import range
from builtins import object
import logging
import time
import threading

import bluepy.btle as btle
import asyncio
import random
from queue import Queue

_LOGGER = logging.getLogger(__name__)

class UUIDS(object):
    FIRMWARE_VERSION   = btle.UUID('64ac0001-4a4b-4b58-9f37-94d3c52ffdf7')

    BATTERY_LEVEL      = btle.UUID('00002A19-0000-1000-8000-00805F9B34FB')

    APP_CHALLENGE      = btle.UUID('64AC0002-4A4B-4B58-9F37-94D3C52FFDF7')
    DEVICE_CHALLENGE   = btle.UUID('64AC0003-4A4B-4B58-9F37-94D3C52FFDF7')
    DEVICE_RESPONSE    = btle.UUID('64AC0004-4A4B-4B58-9F37-94D3C52FFDF7')

    CONFIG             = btle.UUID('06ef0002-2e06-4b79-9e33-fce2c42805ec')
    PROBE1_TEMPERATURE = btle.UUID('06ef0002-2e06-4b79-9e33-fce2c42805ec')
    PROBE1_THRESHOLD   = btle.UUID('06ef0003-2e06-4b79-9e33-fce2c42805ec')
    PROBE2_TEMPERATURE = btle.UUID('06ef0004-2e06-4b79-9e33-fce2c42805ec')
    PROBE2_THRESHOLD   = btle.UUID('06ef0005-2e06-4b79-9e33-fce2c42805ec')
    PROBE3_TEMPERATURE = btle.UUID('06ef0006-2e06-4b79-9e33-fce2c42805ec')
    PROBE3_THRESHOLD   = btle.UUID('06ef0007-2e06-4b79-9e33-fce2c42805ec')
    PROBE4_TEMPERATURE = btle.UUID('06ef0008-2e06-4b79-9e33-fce2c42805ec')
    PROBE4_THRESHOLD   = btle.UUID('06ef0009-2e06-4b79-9e33-fce2c42805ec')
    HEATING_ELEMENTS   = btle.UUID('6c91000a-58dc-41c7-943f-518b278ceaaa')


class IDevicePeripheral(btle.Peripheral):
    encryption_key = None
    has_battery = None
    has_heating_element = None
    authenticated = False

    def __init__(self, address, name, num_probes, has_battery=True, has_heating_element=False):
        """
        Connects to the device given by address performing necessary authentication
        """
        btle.Peripheral.__init__(self)
        self.name = name
        self.address = address
        self.has_battery = has_battery
        self.has_heating_element = has_heating_element
        self.num_probes = num_probes
        self.heatingEleVal = 0
        self.temps = {1: 0, 2: 0, 3: 0, 4: 0}
        self.battery = 0
        

    def characteristic(self, uuid):
        """
        Returns the characteristic for a given uuid.
        """
        for c in self.characteristics:
            if c.uuid == uuid:
                return c

    def authenticate(self):
        """
        Performs iDevices challenge/response handshake. Returns if handshake succeeded
        Works for all devices using this handshake, no key required
        (copied from https://github.com/kins-dev/igrill-smoker, thanks for the tip!)
        """
        _LOGGER.debug("Connecting...")
        self.connect(self.address)
        _LOGGER.debug("Setting security...")
        # iDevice devices require bonding. I don't think this will give us bonding
        # if no bonding exists, so please use bluetoothctl to create a bond first
        self.setSecurityLevel('medium')
        _LOGGER.debug("Grabbing characteristics...")

        # enumerate all characteristics so we can look up handles from uuids
        self.characteristics = self.getCharacteristics()

        # Set handle for reading battery level
        if self.has_battery:
            self.battery_char = self.characteristic(UUIDS.BATTERY_LEVEL)

        # Set handle for reading main elements
        if self.has_heating_element:
            self.heating_elements = self.characteristic(UUIDS.HEATING_ELEMENTS)

        # find characteristics for temperature
        self.temp_chars = {}

        for probe_num in range(1, self.num_probes + 1):
            temp_char_name = "PROBE{}_TEMPERATURE".format(probe_num)
            temp_char = self.characteristic(getattr(UUIDS, temp_char_name))
            self.temp_chars[probe_num] = temp_char
            _LOGGER.debug("Added probe with index {0}, name {1}, and UUID {2}".format(probe_num, temp_char_name, temp_char))
        _LOGGER.debug("Authenticating...")

        # send app challenge (16 bytes) (must be wrapped in a bytearray)
        challenge = bytes(b'\0' * 16)
        _LOGGER.debug("Sending key of all 0's")
        self.characteristic(UUIDS.APP_CHALLENGE).write(challenge, True)

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
        encrypted_device_challenge = self.characteristic(UUIDS.DEVICE_CHALLENGE).read()
        self.characteristic(UUIDS.DEVICE_RESPONSE).write(encrypted_device_challenge, True)

        _LOGGER.debug("Authenticated")
        self.authenticated = True
        return True

    def _update(self):
        try:
            if self.authenticated:
                self.heatingEleVal = bytearray(self.heating_elements.read()) if self.has_heating_element else 0
                for probe_num, temp_char in list(self.temp_chars.items()):
                    temp = bytearray(temp_char.read())[1] * 256
                    temp += bytearray(temp_char.read())[0]
                    self.temps[probe_num] = float(temp) if float(temp) != 63536.0 else 0
                self.battery = float(bytearray(self.battery_char.read())[0])

            else:
                self.authenticate()
        except Exception as ex:
            # If the sensor is off, than retry connecting
            self.authenticated = False

    async def update(self):
        await asyncio.get_event_loop().run_in_executor(None, self._update)
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