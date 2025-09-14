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
from aioxcom import (
    XcomFormat,
    XcomLevel,
    XcomCategory,
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

        _LOGGER.info(f"Add {len(target_entities)} {target_platform} entities for installation '{self._coordinator.config[CONF_PORT]}'")

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
    
    
    def _get_entity_platform(self, entity):
        """
        Determine what platform an entry should be added into
        """
        
        # Is it a switch/select/number/time config or control entity? 
        if entity.category == XcomCategory.PARAMETER:
            if entity.level==XcomLevel.VO:
                return Platform.SENSOR
            
            match entity.format:
                case XcomFormat.BOOL:
                    return Platform.SWITCH
                
                case XcomFormat.SHORT_ENUM | XcomFormat.LONG_ENUM:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a switch
                    if len(entity.options or []) == 2:
                        if all(k in SWITCH_VALUES_ALL and v in SWITCH_VALUES_ALL for k,v in entity.options.items()):
                            return Platform.SWITCH
                    
                    # With more values or not of ON/OFF type it becomes a Select
                    return Platform.SELECT
                
                case XcomFormat.INT32:
                    if entity.default=="S" or entity.min=="S" or entity.max=="S":
                        return Platform.BUTTON
                    elif entity.unit == "Seconds":
                        return Platform.DATETIME
                    elif entity.unit == "Minutes":
                        return Platform.TIME
                    else:
                        return Platform.NUMBER

                case XcomFormat.FLOAT:
                    return Platform.NUMBER
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.format}) in _get_entity_platform")
                    return None
                
        elif entity.category == XcomCategory.INFO:
            match entity.format:
                case XcomFormat.BOOL:
                    return Platform.BINARY_SENSOR
                
                case XcomFormat.SHORT_ENUM | XcomFormat.LONG_ENUM:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a binary sensor
                    if len(entity.options or []) == 2:
                        if all(k in BINARY_SENSOR_VALUES_ALL and v in BINARY_SENSOR_VALUES_ALL for k,v in entity.options.items()):
                            return Platform.BINARY_SENSOR
                    
                    # With more values or not of ON/OFF type it becomes a general sensor
                    return Platform.SENSOR
                
                case XcomFormat.FLOAT | XcomFormat.INT32:
                    return Platform.SENSOR
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.format}) in _get_entity_platform")
                    return None
                
        else:
            _LOGGER.warning(f"Unexpected entity obj_type ({entity.obj_type}) in _get_entity_platform")
            return None
    

