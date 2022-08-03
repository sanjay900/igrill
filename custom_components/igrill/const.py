from __future__ import annotations

from datetime import timedelta
from enum import Enum

import logging
from typing import Final

CONF_SENSORTYPE = "sensortype"
from .igrill import (
    IGrillMiniPeripheral,
    IGrillV2Peripheral,
    IGrillV3Peripheral,
    Pulse2000Peripheral,
)

CONF_HCI_INTERFACE = "hci_interface"
CONF_BT_INTERFACE = "bt_interface"
SERVICE_IGRILL: Final = "igrill"
SCAN_INTERVAL = timedelta(seconds=10)
LOGGER = logging.getLogger(__package__)
DOMAIN = "igrill"


class SensorType(Enum):
    IGRILL_MINI = "igrill_mini"
    IGRILL_V2 = "igrill_v2"
    IGRILL_V3 = "igrill_v3"
    PULSE_2000 = "pulse_2000"


DEVICE_TYPES = {
    SensorType.IGRILL_MINI.value: IGrillMiniPeripheral,
    SensorType.IGRILL_V2.value: IGrillV2Peripheral,
    SensorType.IGRILL_V3.value: IGrillV3Peripheral,
    SensorType.PULSE_2000.value: Pulse2000Peripheral,
}
