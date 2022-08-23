from __future__ import annotations

from datetime import timedelta
from enum import Enum

CONF_SENSORTYPE = "sensortype"
DEVICE_TIMEOUT = 10
DOMAIN = "igrill_ble"


class SensorType(Enum):
    IGRILL_MINI = "igrill_mini"
    IGRILL_MINI_2 = "igrill_mini_2"
    IGRILL_V2 = "igrill_v2"
    IGRILL_V2_2 = "igrill_v2_2"
    IGRILL_V3 = "igrill_v3"
    KITCHEN_THERMOMETER = "kt"
    KITCHEN_THERMOMETER_MINI = "kt_mini"
    PULSE_1000 = "pulse_1000"
    PULSE_2000 = "pulse_2000"
