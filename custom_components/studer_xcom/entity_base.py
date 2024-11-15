import logging
import async_timeout

from datetime import timedelta
from typing import Any

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import homeassistant.helpers.entity_registry as entity_registry

from homeassistant.const import (
    CONF_PORT,
)

from .const import (
    DOMAIN,
    PLATFORMS,
    HELPER,
    CONF_OPTIONS,
    BINARY_SENSOR_VALUES_ON,
    BINARY_SENSOR_VALUES_OFF,
    BINARY_SENSOR_VALUES_ALL,
    SWITCH_VALUES_ON,
    SWITCH_VALUES_OFF,
    SWITCH_VALUES_ALL,
)
from .coordinator import (
    StuderCoordinatorFactory,
    StuderCoordinator
)
from aioxcom import (
    FORMAT,
    OBJ_TYPE,
)

_LOGGER = logging.getLogger(__name__)


class StuderEntityHelperFactory:
    
    @staticmethod
    def create(hass: HomeAssistant, config_entry: ConfigEntry):
        """
        Get existing helper for a config entry, or create a new one if it does not yet exist
        """
    
        # Get properties from the config_entry
        port = config_entry.data[CONF_PORT]
        options = config_entry.options

        install_id = port

        if not HELPER in hass.data[DOMAIN]:
            hass.data[DOMAIN][HELPER] = {}
            
        # already created?
        helper = hass.data[DOMAIN][HELPER].get(install_id, None)
        if not helper:
            # Get an instance of our helper. This is unique to this install_id
            helper = StuderEntityHelper(hass, config_entry, install_id, options)
            hass.data[DOMAIN][HELPER][install_id] = helper
            
        return helper


class StuderEntityHelper:
    """My custom helper to provide common functions."""
    
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, install_id, options):
        self.install_id = install_id
        self.options = options

        # Get an instance of the DabPumpsCoordinator for this install_id
        self.coordinator = StuderCoordinatorFactory.create(hass, config_entry)

        # Get entity registry
        self.entity_registry = entity_registry.async_get(hass)
        
    
    async def async_setup_entry(self, target_platform, target_class, async_add_entities: AddEntitiesCallback):
        """
        Setting up the adding and updating of sensor and binary_sensor entities
        """    
        # Get data from the coordinator
        entity_map = self.coordinator.data
        
        if not entity_map:
            # If data returns False or is empty, log an error and return
            _LOGGER.warning(f"Failed to fetch entity data")
            return
        
        other_platforms = [p for p in PLATFORMS if p != target_platform]
        
        # Iterate all statusses to create sensor entities
        ha_entities = []
        for entity in entity_map.values():
            
            platform = self._get_entity_platform(entity)
            
            if platform != target_platform:
                # This status will be handled via another platform
                continue
                
            # Create a Sensor, Binary_Sensor, Number, Select, Switch or other entity for this status
            ha_entity = None                
            try:
                ha_entity = target_class(self.coordinator, self.install_id, entity)
                ha_entities.append(ha_entity)
            except Exception as  ex:
                _LOGGER.warning(f"Could not instantiate {platform} entity class for {entity.object_id}. Details: {ex}")

            # See if new entity already existed under another platform. If so, then remove the old entity.
            if ha_entity:
                for p in other_platforms:
                    try:
                        ha_entity_id = self.entity_registry.async_get_entity_id(p, DOMAIN, ha_entity.unique_id)
                        if ha_entity_id:
                            _LOGGER.info(f"Remove obsolete {ha_entity_id} that is replaced by {platform}.{ha_entity.unique_id}")
                            self.entity_registry.async_remove(ha_entity_id)

                        ha_entity_id = self.entity_registry.async_get_entity_id(p, DOMAIN, ha_entity.object_id)
                        if ha_entity_id:
                            _LOGGER.info(f"Remove obsolete {ha_entity_id} that is replaced by {platform}.{ha_entity.unique_id}")
                            self.entity_registry.async_remove(ha_entity_id)
                    except Exception as  ex:
                        _LOGGER.warning(f"Could not remove obsolete {p}.{ha_entity.unique_id} entity. Details: {ex}")

        _LOGGER.info(f"Add {len(ha_entities)} {target_platform} entities for installation '{self.install_id}'")
        if ha_entities:
            async_add_entities(ha_entities)
    
    
    def _get_entity_platform(self, entity):
        """
        Determine what platform an entry should be added into
        """
        
        # Is it a switch/select/number/time config or control entity? 
        if entity.obj_type == OBJ_TYPE.PARAMETER:
            match entity.format:
                case FORMAT.BOOL:
                    return Platform.SWITCH
                
                case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a switch
                    if len(entity.options or []) == 2:
                        if all(k in SWITCH_VALUES_ALL and v in SWITCH_VALUES_ALL for k,v in entity.options.items()):
                            return Platform.SWITCH
                    
                    # With more values or not of ON/OFF type it becomes a Select
                    return Platform.SELECT
                
                case FORMAT.INT32:
                    if entity.default=="S" or entity.min=="S" or entity.max=="S":
                        return Platform.BUTTON
                    elif entity.unit == "Seconds":
                        return Platform.DATETIME
                    elif entity.unit == "Minutes":
                        return Platform.TIME
                    else:
                        return Platform.NUMBER

                case FORMAT.FLOAT:
                    return Platform.NUMBER
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.format}) in _get_entity_platform")
                    return None
                
        elif entity.obj_type == OBJ_TYPE.INFO:
            match entity.format:
                case FORMAT.BOOL:
                    return Platform.BINARY_SENSOR
                
                case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                    # With exactly 2 possible values that are of ON/OFF type it becomes a binary sensor
                    if len(entity.options or []) == 2:
                        if all(k in BINARY_SENSOR_VALUES_ALL and v in BINARY_SENSOR_VALUES_ALL for k,v in entity.options.items()):
                            return Platform.BINARY_SENSOR
                    
                    # With more values or not of ON/OFF type it becomes a general sensor
                    return Platform.SENSOR
                
                case FORMAT.FLOAT | FORMAT.INT32:
                    return Platform.SENSOR
                
                case _:
                    _LOGGER.warning(f"Unexpected entity format ({entity.format}) in _get_entity_platform")
                    return None
                
        else:
            _LOGGER.warning(f"Unexpected entity obj_type ({entity.obj_type}) in _get_entity_platform")
            return None
    

class StuderEntity(Entity):
    """
    Common funcionality for all Studer Entities:
    (StuderSensor, StuderBinarySensor, StuderNumber, StuderSelect, StuderSwitch)
    """
    
    def __init__(self, coordinator, entity):
        self._coordinator = coordinator
        self._entity = entity
        self._attr_unit = self._convert_to_unit()
        self._unit_weight = 1


    def _convert_to_unit(self):
        """Convert from Studer units to Home Assistant units"""
        match self._entity.unit:
            case '°C':          return '°C' 
            case '°F':          return '°F'
            case 'days':        return 'day'
            case 'h':           return 'h'
            case 'hours':       return 'h'
            case 'min':         return 'min'
            case 'minutes':     return 'min'
            case 'Minutes':     return 'min'
            case 's':           return 's'
            case 'sec':         return 's'
            case 'seconds':     return 's'
            case 'Seconds':     return 's'
            case '%':           return '%'
            case '% SOC':       return '%'
            case 'V':           return 'V'
            case 'Vac':         return 'V'
            case 'Vdc':         return 'V'
            case 'A':           return 'A'
            case 'Aac':         return 'A'
            case 'Adc':         return 'A'
            case 'Ah':          return 'Ah'
            case 'kAh':         return 'kAh'
            case 'mW':          return 'mW'
            case 'W':           return 'W'
            case 'kW':          return 'kW'
            case 'kWh':         return 'kWh'
            case 'MWh':         return 'MWh'
            case 'VA':          return 'VA'
            case 'kVA':         self._unit_weight = 1000; return 'VA'
            case 'Hz':          return 'Hz'
            case 'Ctmp':        return None
            case 'Cdyn':        return None
            case '':            return None
            case 'None' | None: return None
            
            case _:
                _LOGGER.warn(f"Encountered a unit or measurement '{self._entity.unit}' for '{self._entity.unique_id}' that may not be supported by Home Assistant. Please contact the integration developer to have this resolved.")
                return self._entity.unit
    
    
    def get_unit(self):
        return self._attr_unit
        
    
    def get_icon(self):
        """Convert from HA unit to icon"""
        match self._attr_unit:
            case '°C':      return 'mdi:thermometer'
            case '°F':      return 'mdi:thermometer'
            case 'min':     return 'mdi:timer-sand'
            case 'day':     return 'mdi:timer'
            case 'h':       return 'mdi:timer'
            case 'min':     return 'mdi:timer'
            case 's':       return 'mdi:timer'
            case '%':       return 'mdi:percent'
            case 'V':       return 'mdi:lightning-bolt'
            case 'A':       return 'mdi:lightning-bolt'
            case 'Ah':      return 'mdi:lightning'
            case 'kAh':     return 'mdi:lightning'
            case 'mW':      return 'mdi:power-plug'
            case 'W':       return 'mdi:power-plug'
            case 'kW':      return 'mdi:power-plug'
            case 'Wh':      return 'mdi:lightning'
            case 'kWh':     return 'mdi:lightning'
            case 'MWh':     return 'mdi:lightning'
            case 'VA':      return 'mdi:power-plug'
            case 'kVA':     return 'mdi:power-plug'
            case 'Hz':      return None
            case _:         return None
    
    
    def get_number_device_class(self):
        """Convert from HA unit to NumberDeviceClass"""
        if self._entity.format == FORMAT.SHORT_ENUM or self._entity.format == FORMAT.LONG_ENUM:
            return NumberDeviceClass.ENUM
            
        match self._entity.unit:
            case '°C':      return NumberDeviceClass.TEMPERATURE
            case '°F':      return NumberDeviceClass.TEMPERATURE
            case 'min':     return NumberDeviceClass.DURATION
            case 'day':     return NumberDeviceClass.DURATION
            case 'h':       return NumberDeviceClass.DURATION
            case 'min':     return NumberDeviceClass.DURATION
            case 's':       return NumberDeviceClass.DURATION
            case '%':       return NumberDeviceClass.BATTERY
            case 'V':       return NumberDeviceClass.VOLTAGE
            case 'A':       return NumberDeviceClass.CURRENT
            case 'VA':      return NumberDeviceClass.APPARENT_POWER
            case 'kVA':     return NumberDeviceClass.APPARENT_POWER
            case 'mW':      return NumberDeviceClass.POWER
            case 'W':       return NumberDeviceClass.POWER
            case 'kW':      return NumberDeviceClass.POWER
            case 'Wh':      return NumberDeviceClass.ENERGY
            case 'kWh':     return NumberDeviceClass.ENERGY
            case 'MWh':     return NumberDeviceClass.ENERGY
            case 'Hz':      return NumberDeviceClass.FREQUENCY
            case 'Ah':      return None
            case 'kAh':     return None
            case _:         return None
    
    
    def get_sensor_device_class(self):
        """Convert from HA unit to SensorDeviceClass"""
        if self._entity.format == FORMAT.SHORT_ENUM or self._entity.format == FORMAT.LONG_ENUM:
            return SensorDeviceClass.ENUM
            
        match self._entity.unit:
            case '°C':      return SensorDeviceClass.TEMPERATURE
            case '°F':      return SensorDeviceClass.TEMPERATURE
            case 'min':     return SensorDeviceClass.DURATION
            case 'day':     return SensorDeviceClass.DURATION
            case 'h':       return SensorDeviceClass.DURATION
            case 'min':     return SensorDeviceClass.DURATION
            case 's':       return SensorDeviceClass.DURATION
            case '%':       return SensorDeviceClass.BATTERY
            case 'V':       return SensorDeviceClass.VOLTAGE
            case 'A':       return SensorDeviceClass.CURRENT
            case 'VA':      return SensorDeviceClass.APPARENT_POWER
            case 'kVA':     return SensorDeviceClass.APPARENT_POWER
            case 'mW':      return SensorDeviceClass.POWER
            case 'W':       return SensorDeviceClass.POWER
            case 'kW':      return SensorDeviceClass.POWER
            case 'Wh':      return SensorDeviceClass.ENERGY
            case 'kWh':     return SensorDeviceClass.ENERGY
            case 'MWh':     return SensorDeviceClass.ENERGY
            case 'Hz':      return SensorDeviceClass.FREQUENCY
            case 'Ah':      return None
            case 'kAh':     return None
            case _:         return None
    
    
    def get_sensor_state_class(self):
        # Return StateClass=None for Enum or Label
        if self._entity.format == FORMAT.SHORT_ENUM or self._entity.format == FORMAT.LONG_ENUM:
            return None
        
        # Return StateClass=None for params that are a setting, unlikely to change often
        if self._entity.obj_type == OBJ_TYPE.PARAMETER:
            return None
        
        # Return StateClass=None for some specific entities
        nrs_none = []
        if self._entity.nr in nrs_none:
            return None
        
        # Return StateClass=Total or Total_Increasing for some specific entities
        nrs_t = []
        nrs_ti = []
        
        if self._entity.nr in nrs_t:
            return SensorStateClass.TOTAL
            
        elif self._entity.nr in nrs_ti:
            return SensorStateClass.TOTAL_INCREASING

        # Return StateClass=None depending on device-class
        dcs_none = [SensorDeviceClass.ENERGY]
        if self.get_sensor_device_class() in dcs_none:
            return None

        # All other cases: StateClass=measurement            
        return SensorStateClass.MEASUREMENT
    
    
    def get_entity_category(self):
        
        # Return None for some specific entities we always want as sensors 
        # even if they would fail some of the tests below
        nrs_none = [
        ]
        if self._entity.nr in nrs_none:
            return None
            
        # Return None for params in groups associated with Control
        # and that a customer is allowed to change.
        # Leads to the entities being added under 'Controls'
        levels_control = []
        if self._entity.level in levels_control:
            return None
        
        # Return CONFIG for params in groups associated with configuration
        # Leads to the entities being added under 'Configuration'
        # Typically intended for restart or update functionality
        nrs_config = []
        if self._entity.nr in nrs_config:
            return EntityCategory.CONFIG
            
        # Return DIAGNOSTIC for some specific entries associated with others that are DIAGNOSTIC
        # Leads to the entities being added under 'Diagnostic'
        nrs_diag = []
        if self._entity.nr in nrs_diag:
            return EntityCategory.DIAGNOSTIC
        
        # Return None for params that are a setting
        # Leads to the entities being added under 'Controls'
        if self._entity.obj_type == OBJ_TYPE.PARAMETER:
            return None
        
        # Return None for all others
        return None
    
    
    def get_number_step(self):
        match self._attr_unit:
            case 's':
                candidates = [3600, 60, 1]
            case 'min':
                candidates = [60, 1]
            case 'h':
                candidates = [24, 1]
            case _:
                candidates = [1000, 100, 10, 1]
                
        # find first candidate where min, max and diff are all dividable by (without remainder)
        if self._entity.min is not None and self._entity.max is not None:
            min = int(self._entity.min)
            max = int(self._entity.max)
            diff = max - min
            
            for c in candidates:
                if (min % c == 0) and (max % c == 0) and (diff % c == 0):
                    return c
                
        return None

