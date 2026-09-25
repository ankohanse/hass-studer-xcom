import logging
import homeassistant.helpers.entity_registry as entity_registry

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import (
    CONF_PORT,
)

from .const import (
    BINARY_SENSOR_VALUES_ON,
    BINARY_SENSOR_VALUES_OFF,
    BINARY_SENSOR_VALUES_ALL,
    SWITCH_VALUES_ON,
    SWITCH_VALUES_OFF,
    SWITCH_VALUES_ALL,
)
from .coordinator import (
    StuderCoordinatorFactory,
    StuderCoordinator,
    StuderEntityData,
)
from pystudernext import (
    StuderAccess,
    StuderDataType,
    StuderUserLevel,
)

_LOGGER = logging.getLogger(__name__)


class StuderEntityHelperFactory:
    
    @staticmethod
    async def async_create(hass: HomeAssistant, config_entry: ConfigEntry):
        """
        Get entity helper for a config entry.
        The entry is short lived (only during init) and does not contain state data,
        therefore no need to cache it in hass.data
        """
    
        # Get an instance of the DabPumpsCoordinator
        coordinator = await StuderCoordinatorFactory.async_create(hass, config_entry)
    
        # Get an instance of our helper. This is unique to this config_entry
        return StuderEntityHelper(hass, coordinator)


class StuderEntityHelper:
    """My custom helper to provide common functions."""
    
    def __init__(self, hass: HomeAssistant, coordinator: StuderCoordinator):
        self._coordinator = coordinator
        self._entity_registry = entity_registry.async_get(hass)
        
    
    async def async_setup_entry(self, target_platform, target_class, async_add_entities: AddEntitiesCallback):
        """
        Setting up the adding and updating of sensor and binary_sensor entities
        """    
        # Get data from the coordinator
        entity_map: dict[str,StuderEntityData] = self._coordinator.data
        
        if not entity_map:
            # If data returns False or is empty, log an error and return
            _LOGGER.warning(f"Failed to fetch entity data")
            return
        
        # Iterate all statusses to create sensor entities
        ha_entities = []
        valid_unique_ids: list[str] = []
        target_entities: list[StuderEntityData] = [e for e in entity_map.values() if target_platform==self._get_entity_platform(e)]

        for entity in target_entities:
            # Create a Sensor, Binary_Sensor, Number, Select, Switch or other entity for this status
            ha_entity = None                
            try:
                ha_entity = target_class(self._coordinator, entity)
                ha_entities.append(ha_entity)
                
                valid_unique_ids.append(entity.unique_id)

            except Exception as  ex:
                _LOGGER.warning(f"Could not instantiate {target_platform} entity class for {entity.object_id}. Details: {ex}")

        # Remember valid unique_ids per platform so we can do an entity cleanup later
        self._coordinator.set_valid_unique_ids(target_platform, valid_unique_ids)

        # Now add the entities to the entity_registry
        if ha_entities:
            async_add_entities(ha_entities)
    
    
    def _get_entity_platform(self, entity: StuderEntityData):
        """
        Determine what platform an entry should be added into
        """
        
        # Is it a button entity and do we have enough rights to write?
        if entity.datapoint.access in [StuderAccess.WRITE] and \
           entity.datapoint.userlevel_w <= StuderUserLevel.EXPERT:
            
            match entity.datapoint.data_type:
                case StuderDataType.SIGNAL:
                    return Platform.BUTTON
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.datapoint.data_type}) in _get_entity_platform")
                    return None

        # Is it a button/switch/select/number/time entity and do we have enough rights to read and write? 
        elif entity.datapoint.access in [StuderAccess.READ_WRITE] and \
             entity.datapoint.userlevel_r <= StuderUserLevel.EXPERT and \
             entity.datapoint.userlevel_w <= StuderUserLevel.EXPERT:

            match entity.datapoint.data_type:
                case StuderDataType.BOOL:
                    return Platform.SWITCH
                
                case StuderDataType.ENUM16 | StuderDataType.ENUM32:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a switch
                    if len(entity.datapoint.enum_options or []) == 2:
                        if all(k in SWITCH_VALUES_ALL and v in SWITCH_VALUES_ALL for k,v in entity.datapoint.enum_options.items()):
                            return Platform.SWITCH
                    
                    # With more values or not of ON/OFF type it becomes a Select
                    return Platform.SELECT
                
                case StuderDataType.INT16 | StuderDataType.INT32 | StuderDataType.INT64 | \
                     StuderDataType.UINT16 | StuderDataType.UINT32 | StuderDataType.UINT64:
                    if entity.datapoint.default=="S" or entity.datapoint.min=="S" or entity.datapoint.max=="S":
                        return Platform.BUTTON
                    elif entity.datapoint.unit == "Seconds":
                        return Platform.DATETIME
                    elif entity.datapoint.unit == "Minutes":
                        return Platform.TIME
                    else:
                        return Platform.NUMBER

                case StuderDataType.FLOAT32 | StuderDataType.FLOAT64:
                    return Platform.NUMBER
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.datapoint.data_type}) in _get_entity_platform")
                    return None

        # Is it a (binary) sensor entity, and do we have enough rights to read?
        # Also handles fallthrough from previous access tests.
        elif entity.datapoint.access in [StuderAccess.READ, StuderAccess.READ_WRITE] and \
             entity.datapoint.userlevel_r <= StuderUserLevel.EXPERT:

            match entity.datapoint.data_type:
                case StuderDataType.BOOL:
                    return Platform.BINARY_SENSOR
                
                case StuderDataType.ENUM16 | StuderDataType.ENUM32:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a binary sensor
                    if len(entity.datapoint.enum_options or []) == 2:
                        if all(k in BINARY_SENSOR_VALUES_ALL and v in BINARY_SENSOR_VALUES_ALL for k,v in entity.datapoint.enum_options.items()):
                            return Platform.BINARY_SENSOR
                    
                    # With more values or not of ON/OFF type it becomes a general sensor
                    return Platform.SENSOR
                
                case StuderDataType.FLOAT32 | StuderDataType.FLOAT64 | \
                     StuderDataType.INT16 | StuderDataType.INT32 | StuderDataType.INT64 | \
                     StuderDataType.UINT16 | StuderDataType.UINT32 | StuderDataType.UINT64 | \
                     StuderDataType.STRING:

                    # General sensor
                    return Platform.SENSOR
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.datapoint.data_type}) in _get_entity_platform")
                    return None               
        
        else:
            _LOGGER.warning(f"Unexpected entity access ({entity.datapoint.access}) in _get_entity_platform")
            return None
    

