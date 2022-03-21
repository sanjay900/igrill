from __future__ import annotations

from datetime import timedelta

import logging
from typing import Final
CONF_SENSORTYPE = "sensortype"
from .igrill import IGrillMiniPeripheral, IGrillV2Peripheral, IGrillV3Peripheral, Pulse2000Peripheral, UUIDS

DEVICE_TYPES = {'igrill_mini': IGrillMiniPeripheral,
                    'igrill_v2': IGrillV2Peripheral,
                    'igrill_v3': IGrillV3Peripheral,
                    'pulse_2000': Pulse2000Peripheral}

SERVICE_IGRILL: Final = "igrill"
SCAN_INTERVAL = timedelta(seconds=10)
LOGGER = logging.getLogger(__package__)
DOMAIN = "igrill"