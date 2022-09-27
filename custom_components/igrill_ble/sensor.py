"""Support for displaying collected data over SNMP."""
import logging
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_HW_VERSION,
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SW_VERSION,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

from .igrill import IDevicePeripheral
from .const import DOMAIN

from sensor_state_data import (
    DeviceClass,
    DeviceKey,
    SensorDeviceInfo,
    SensorUpdate,
    Units,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = {
    (DeviceClass.TEMPERATURE, Units.TEMP_FAHRENHEIT): SensorEntityDescription(
        key=f"{DeviceClass.TEMPERATURE}_{Units.TEMP_CELSIUS}",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=TEMP_FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (DeviceClass.TEMPERATURE, Units.TEMP_CELSIUS): SensorEntityDescription(
        key=f"{DeviceClass.TEMPERATURE}_{Units.TEMP_CELSIUS}",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=TEMP_CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (DeviceClass.BATTERY, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{DeviceClass.BATTERY}_{Units.PERCENTAGE}",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (
        DeviceClass.SIGNAL_STRENGTH,
        Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    ): SensorEntityDescription(
        key=f"{DeviceClass.SIGNAL_STRENGTH}_{Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT}",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    (DeviceClass.GAS, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{DeviceClass.GAS}_{Units.PERCENTAGE}",
        device_class=DeviceClass.GAS,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (None, Units.PERCENTAGE): SensorEntityDescription(
        key=str(Units.PERCENTAGE),
        device_class=None,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
}


def sensor_device_info_to_hass(
    sensor_device_info: SensorDeviceInfo,
) -> DeviceInfo:
    """Convert a sensor device info to a sensor device info."""
    hass_device_info = DeviceInfo({})
    if sensor_device_info.name is not None:
        hass_device_info[ATTR_NAME] = sensor_device_info.name
    if sensor_device_info.manufacturer is not None:
        hass_device_info[ATTR_MANUFACTURER] = sensor_device_info.manufacturer
    if sensor_device_info.model is not None:
        hass_device_info[ATTR_MODEL] = sensor_device_info.model
    if sensor_device_info.sw_version is not None:
        hass_device_info[ATTR_SW_VERSION] = sensor_device_info.sw_version
    if sensor_device_info.sw_version is not None:
        hass_device_info[ATTR_HW_VERSION] = sensor_device_info.hw_version
    return hass_device_info


def device_key_to_bluetooth_entity_key(
    device_key: DeviceKey,
) -> PassiveBluetoothEntityKey:
    """Convert a device key to an entity key."""
    return PassiveBluetoothEntityKey(device_key.key, device_key.device_id)


def sensor_update_to_bluetooth_data_update(
    sensor_update: SensorUpdate,
) -> PassiveBluetoothDataUpdate:
    """Convert a sensor update to a bluetooth data update."""
    return PassiveBluetoothDataUpdate(
        devices={
            device_id: sensor_device_info_to_hass(device_info)
            for device_id, device_info in sensor_update.devices.items()
        },
        entity_descriptions={
            device_key_to_bluetooth_entity_key(device_key): SENSOR_DESCRIPTIONS[
                (description.device_class, description.native_unit_of_measurement)
            ]
            for device_key, description in sensor_update.entity_descriptions.items()
            if description.native_unit_of_measurement
        },
        entity_data={
            device_key_to_bluetooth_entity_key(device_key): sensor_values.native_value
            for device_key, sensor_values in sensor_update.entity_values.items()
        },
        entity_names={
            device_key_to_bluetooth_entity_key(device_key): sensor_values.name
            for device_key, sensor_values in sensor_update.entity_values.items()
        },
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IGrill Sensors."""
    igrill: IDevicePeripheral = hass.data[DOMAIN][entry.entry_id]
    created: set[PassiveBluetoothEntityKey] = set()

    @callback
    def _async_add_or_update_entities(
        sensor_data: SensorUpdate,
    ) -> None:
        """Listen for new entities."""
        if sensor_data is None:
            return
        data = sensor_update_to_bluetooth_data_update(sensor_data)
        entities: list[PassiveBluetoothProcessorEntity] = []
        for entity_key, description in data.entity_descriptions.items():
            if entity_key not in created:
                entities.append(
                    IGrillSensorEntity(entity_key, description, igrill, sensor_data)
                )
                created.add(entity_key)
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(igrill.async_add_listener(_async_add_or_update_entities))


class IGrillSensorEntity(
    SensorEntity,
):
    _attr_has_entity_name = True
    _attr_should_poll = False
    """Representation of a iGrill sensor."""

    def __init__(
        self,
        entity_key: PassiveBluetoothEntityKey,
        description: EntityDescription,
        data: IDevicePeripheral,
        entity_data: PassiveBluetoothDataUpdate,
    ) -> None:
        self.entity_key = entity_key
        self.entity_description = description
        self.data = data

        passive_update = sensor_update_to_bluetooth_data_update(entity_data)
        device_id = entity_key.device_id
        address = data.address
        devices = passive_update.devices
        key = entity_key.key
        if device_id in devices:
            base_device_info = devices[device_id]
        else:
            base_device_info = DeviceInfo({})
        if device_id:
            self._attr_device_info = base_device_info | DeviceInfo(
                {ATTR_IDENTIFIERS: {(DOMAIN, f"{address}-{device_id}")}}
            )
            self._attr_unique_id = f"{address}-{key}-{device_id}"
        else:
            self._attr_device_info = base_device_info | DeviceInfo(
                {ATTR_IDENTIFIERS: {(DOMAIN, address)}}
            )
            self._attr_unique_id = f"{address}-{key}"
        if ATTR_NAME not in self._attr_device_info:
            self._attr_device_info[ATTR_NAME] = data.bt_name
        self._attr_name = passive_update.entity_names.get(entity_key)
        self.val = passive_update.entity_data[self.entity_key]

    def update(self, update: SensorUpdate):
        passive_update = sensor_update_to_bluetooth_data_update(update)
        if self.entity_key in passive_update.entity_data:
            self.val = passive_update.entity_data[self.entity_key]
            self.schedule_update_ha_state()

    @property
    def native_value(self):
        return self.val

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.data.async_add_listener(lambda data: self.update(data))
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.data.client and self.data.client.is_connected
