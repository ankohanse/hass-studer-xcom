import asyncio
import logging
import math
import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.typing import DiscoveryInfoType

from datetime import timedelta
from datetime import datetime

from collections import defaultdict
from collections import namedtuple

from .const import (
    DOMAIN,
    COORDINATOR,
    MANUFACTURER,
    CONF_OPTIONS,
    CONF_NR,
    CONF_ADDRESS,
    ATTR_XCOM_STATE,
)
from .coordinator import (
    StuderCoordinatorFactory,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData,
)
from .entity_base import (
    StuderEntityHelperFactory,
    StuderEntityHelper,
    StuderEntity,
)
from aioxcom import (
    FORMAT,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of sensor entities
    """
    helper = StuderEntityHelperFactory.create(hass, config_entry)
    await helper.async_setup_entry(Platform.SENSOR, StuderSensor, async_add_entities)


class StuderSensor(CoordinatorEntity, SensorEntity, StuderEntity):
    """
    Representation of a Studer Sensor.
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.SENSOR)
        
        # The unique identifier for this sensor within Home Assistant
        self.object_id = entity.object_id
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)
        self._attr_unique_id = entity.unique_id

        # Standard HA entity attributes        
        self._attr_has_entity_name = True
        self._attr_name = entity.name
        self._name = entity.name
        
        self._attr_state_class = self.get_sensor_state_class()
        self._attr_entity_category = self.get_entity_category()
        self._attr_device_class = self.get_sensor_device_class() 

        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, entity.device_id)},
        )

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_state = None

        # Update value
        self._update_value(entity, True)
    
    
    @property
    def suggested_object_id(self) -> str | None:
        """Return input for object id."""
        return self.object_id
    
    
    @property
    def unique_id(self) -> str:
        """Return a unique ID for use in home assistant."""
        return self._attr_unique_id
    
    
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name
        
        
    @property
    def extra_state_attributes(self) -> dict[str, str | list[str]]:
        """Return the state attributes."""
        if self._xcom_state:
            self._attributes[ATTR_XCOM_STATE] = self._xcom_state

        return self._attributes        
    
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        
        # find the correct device and status corresponding to this sensor
        entity: StuderEntityData|None = self._coordinator.data.get(self.object_id, None)
        if entity:
            # Update value
            if self._update_value(entity, False):
                self.async_write_ha_state()
    
    
    def _update_value(self, entity:StuderEntityData, force:bool=False):
        """Process any changes in value"""
        
        # Transform values according to the metadata params for this status/sensor
        match entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                attr_precision = 3
                attr_digits = 3
                attr_val = round(float(entity.value) * weight, attr_digits) if entity.value!=None and not math.isnan(entity.value) else None
                attr_unit = self.get_unit()

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                attr_precision = None
                attr_val = int(entity.value) * weight if entity.value!=None and not math.isnan(entity.value) else None
                attr_unit = self.get_unit()
                    
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                # Lookup the dict string for the value and otherwise return the value itself
                attr_precision = None
                attr_val = entity.options.get(str(entity.value), entity.value) if entity.value!=None and not math.isnan(entity.value) else None
                attr_unit = None

            case _:
                _LOGGER.warning(f"Unexpected entity format ({entity.format}) for a sensor")
                return
        
        # update value if it has changed
        changed = False

        if force or (self._xcom_state != entity.value):
            self._xcom_state = entity.value
        
        if force or (self._attr_native_value != attr_val):
            if not force:
                _LOGGER.debug(f"Sensor change value {self.object_id} from {self._attr_native_value} to {attr_val}")

            self._attr_native_value = attr_val
            self._attr_native_unit_of_measurement = attr_unit
            self._attr_suggested_display_precision = attr_precision
            
            self._attr_icon = self.get_icon()
            changed = True
        
        return changed
    
