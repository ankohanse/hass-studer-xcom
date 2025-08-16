import logging
import voluptuous as vol

from homeassistant.components.binary_sensor import PLATFORM_SCHEMA as PARENT_PLATFORM_SCHEMA
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    BINARY_SENSOR_VALUES_ON,
    BINARY_SENSOR_VALUES_OFF,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData,
)
from .entity_base import (
    StuderEntity,
)
from .entity_helper import (
    StuderEntityHelperFactory,
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
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
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
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)

        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_device_class = None
        
        self._attr_device_info = DeviceInfo( identifiers = {(DOMAIN, entity.device_id)}, )
        
        # Create all attributes (but with unknown value).
        # After this constructor ends, base class StuderEntity.async_added_to_hass() will 
        # set the value using the restored value from the last HA run.
        self._update_value(entity, True)
    
    
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
    
    
