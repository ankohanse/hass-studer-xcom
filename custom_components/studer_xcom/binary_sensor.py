import asyncio
import logging
import math
import voluptuous as vol

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA as PARENT_PLATFORM_SCHEMA
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.binary_sensor import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity


from datetime import timedelta
from datetime import datetime

from collections import defaultdict
from collections import namedtuple

from .const import (
    DOMAIN,
    COORDINATOR,
    PREFIX_ID,
    PREFIX_NAME,
    MANUFACTURER,
    BINARY_SENSOR_VALUES_ON,
    BINARY_SENSOR_VALUES_OFF,
    BINARY_SENSOR_VALUES_ALL,
    ATTR_XCOM_STATE,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData,
)
from .entity_base import (
    StuderEntityHelperFactory,
    StuderEntity,
)

from aioxcom import (
    FORMAT,
)


_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PARENT_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of binary_sensor entities
    """
    # Add all automatically detected sensors
    helper = StuderEntityHelperFactory.create(hass, config_entry)
    await helper.async_setup_entry(Platform.BINARY_SENSOR, StuderBinarySensor, async_add_entities)


class StuderBinarySensor(CoordinatorEntity, BinarySensorEntity, StuderEntity):
    """
    Representation of a DAB Pumps Binary Sensor.
    
    Could be a sensor that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.BINARY_SENSOR)
        
        # The unique identifier for this sensor within Home Assistant
        self.object_id = entity.object_id
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)
        self._attr_unique_id = entity.unique_id

        # Standard HA entity attributes        
        self._attr_has_entity_name = True
        self._attr_name = entity.name
        self._name = entity.name
        
        self._attr_device_class = None

        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, entity.device_id)},
        )
        
        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_state = None

        # Create all attributes
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
        entity: StuderEntityData|None = self._coordinator.data.get(self.object_id)
        if entity:
            # Update value
            if self._update_value(entity, False):
                self.async_write_ha_state()
    
    
    def _update_value(self, entity:StuderEntityData, force:bool=False):
        """Process any changes in value"""

        match entity.format:
            case FORMAT.BOOL:
                if entity.value == 1:
                    is_on = True
                elif entity.value == 0:
                    is_on = False
                else:
                    is_on = None

            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                # sanity check
                if len(entity.options or []) != 2:
                    _LOGGER.error(f"Unexpected entity options ({entity.options}) for a binary sensor")
                    return
                
                # Lookup the option string for the value and otherwise return the value itself
                val = entity.options.get(str(entity.value), entity.value)
                if val in BINARY_SENSOR_VALUES_ON:
                    is_on = True
                elif val in BINARY_SENSOR_VALUES_OFF:
                    is_on = False
                else:
                    is_on = None
                
            case _:
                _LOGGER.warning(f"Unexpected entity format ({entity.format}) for a binary sensor")
                return
            
        # update value if it has changed
        changed = False

        if force or (self._xcom_state != entity.value):
            
            self._xcom_state = entity.value
        
        if force or (self._attr_is_on != is_on):
            
            self._attr_is_on = is_on
            changed = True
            
        return changed
    
