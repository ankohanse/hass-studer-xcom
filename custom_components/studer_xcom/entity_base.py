import copy
from dataclasses import dataclass
import logging

import math
from typing import Any, Self

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.const import PERCENTAGE
from homeassistant.const import UnitOfApparentPower
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.const import UnitOfElectricPotential
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfFrequency
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfTemperature
from homeassistant.const import UnitOfTime
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import (
    ATTR_XCOM_FLASH_STATE,
    ATTR_XCOM_RAM_STATE,
    ATTR_XCOM_STATE,
    ATTR_STORED_VALUE,
    ATTR_STORED_VALUE_MODIFIED,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData
)
from aioxcom import (
    FORMAT,
    OBJ_TYPE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class StuderEntityExtraData(ExtraStoredData):
    """Object to hold extra stored data."""

    value: Any = None              # Current value as retrieved via api
    value_modified: Any = None     # Updated value to persist the change when an entitiy has been modified (number, select, switch, time)

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the sensor data."""
        return {
            ATTR_STORED_VALUE: self.value,
            ATTR_STORED_VALUE_MODIFIED: self.value_modified,
        }

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize a stored sensor state from a dict."""
        return cls(
            value = restored.get(ATTR_STORED_VALUE),
            value_modified = restored.get(ATTR_STORED_VALUE_MODIFIED),
        )


class StuderEntity(RestoreEntity):
    """
    Common funcionality for all Studer Entities:
    (StuderSensor, StuderBinarySensor, StuderNumber, StuderSelect, StuderSwitch)
    """
    
    def __init__(self, coordinator:StuderCoordinator, entity:StuderEntityData, platform:Platform):
        self._coordinator: StuderCoordinator = coordinator
        self._entity: StuderEntityData = entity
        self._platform: Platform = platform
        self._attr_unit: str|None = self._convert_to_unit()
        self._unit_weight: int = 1

        self.object_id: str = entity.object_id

        # Attributes from Entity base class
        self._attr_unique_id = entity.unique_id
        self._attr_has_entity_name = True
        self._attr_name = entity.name
        self._name = entity.name

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_state: Any = None
        self._xcom_flash_state: Any = None
        self._xcom_ram_state: Any = None
        

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
        """
        Return the state attributes to display in entity attributes.
        """
        if self._xcom_state is not None:
            self._attributes[ATTR_XCOM_STATE] = self._xcom_state

        if self._xcom_flash_state is not None:
            self._attributes[ATTR_XCOM_FLASH_STATE] = self._xcom_flash_state

        if self._xcom_ram_state is not None:
            self._attributes[ATTR_XCOM_RAM_STATE] = self._xcom_ram_state

        return self._attributes        
    

    @property
    def extra_restore_state_data(self) -> StuderEntityExtraData | None:
        """
        Return entity specific state data to be restored on next HA run.
        """
        return StuderEntityExtraData(
            value = self._entity.value,
            value_modified = self._entity.valueModified if self._entity.valueModified != self._entity.value else None,
        )
    

    async def async_added_to_hass(self) -> None:
        """
        Handle when the entity has been added.
        This is called right after the entity was created (with unknown value)
        and sets the inital value to the value restored from the last HA run.
        """
        await super().async_added_to_hass()

        # Get last data from previous HA run                      
        last_state = await self.async_get_last_state()
        last_extra = await self.async_get_last_extra_data()
        
        if last_state and last_extra:
            # Set entity value from restored data
            dict_extra = last_extra.as_dict()

            self._entity.value = dict_extra.get(ATTR_STORED_VALUE)
            self._entity.valueModified = dict_extra.get(ATTR_STORED_VALUE_MODIFIED)

            # Trace and update using the entity value
            if self._entity.valueModified is not None:
                _LOGGER.debug(f"Restore entity '{self.entity_id}' value to {last_state.state} ({self._entity.valueModified} - modified from {self._entity.value})")
            else:
                _LOGGER.debug(f"Restore entity '{self.entity_id}' value to {last_state.state} ({self._entity.value})")

            self._update_value(force=True)
    

    def _update_value(self, force:bool=False):
        """
        Process any changes in value
        
        To be extended by derived entities
        """


    def _convert_to_unit(self) -> str|None:
        """Convert from Studer units to Home Assistant units"""
        match self._entity.unit:
            case '°C':          return UnitOfTemperature.CELSIUS 
            case '°F':          return UnitOfTemperature.FAHRENHEIT
            case 'days':        return UnitOfTime.DAYS
            case 'h':           return UnitOfTime.HOURS
            case 'hours':       return UnitOfTime.HOURS
            case 'min':         return UnitOfTime.MINUTES
            case 'minutes':     return UnitOfTime.MINUTES
            case 'Minutes':     return UnitOfTime.MINUTES
            case 's':           return UnitOfTime.SECONDS
            case 'sec':         return UnitOfTime.SECONDS
            case 'seconds':     return UnitOfTime.SECONDS
            case 'Seconds':     return UnitOfTime.SECONDS
            case '%':           return PERCENTAGE
            case '% SOC':       return PERCENTAGE
            case 'V':           return UnitOfElectricPotential.VOLT
            case 'Vac':         return UnitOfElectricPotential.VOLT
            case 'Vdc':         return UnitOfElectricPotential.VOLT
            case 'A':           return UnitOfElectricCurrent.AMPERE
            case 'Aac':         return UnitOfElectricCurrent.AMPERE
            case 'Adc':         return UnitOfElectricCurrent.AMPERE
            case 'Ah':          return 'Ah'
            case 'kAh':         return 'kAh'
            case 'mW':          return UnitOfPower.MILLIWATT
            case 'W':           return UnitOfPower.WATT
            case 'kW':          return UnitOfPower.KILO_WATT
            case 'Wh':          return UnitOfEnergy.WATT_HOUR
            case 'kWh':         return UnitOfEnergy.KILO_WATT_HOUR
            case 'MWh':         return UnitOfEnergy.MEGA_WATT_HOUR
            case 'VA':          return UnitOfApparentPower.VOLT_AMPERE
            case 'kVA':         self._unit_weight = 1000; return UnitOfApparentPower.VOLT_AMPERE
            case 'Hz':          return UnitOfFrequency.HERTZ
            case 'Ctmp':        return None
            case 'Cdyn':        return None
            case '':            return None
            case 'None' | None: return None
            
            case _:
                _LOGGER.warn(f"Encountered a unit or measurement '{self._entity.unit}' for '{self._entity.unique_id}' that may not be supported by Home Assistant. Please contact the integration developer to have this resolved.")
                return self._entity.unit
    
    
    def get_unit(self) -> str|None:
        return self._attr_unit
        
    
    def get_icon(self) -> str|None:
        """Convert from HA unit to icon"""
        match self._attr_unit:
            case UnitOfTemperature.CELSIUS:         return 'mdi:thermometer'
            case UnitOfTemperature.FAHRENHEIT:      return 'mdi:thermometer'
            case UnitOfTime.DAYS:                   return 'mdi:timer'
            case UnitOfTime.HOURS:                  return 'mdi:timer'
            case UnitOfTime.MINUTES:                return 'mdi:timer-sand'
            case UnitOfTime.SECONDS:                return 'mdi:timer'
            case '%':                               return 'mdi:percent'
            case UnitOfElectricPotential.VOLT:      return 'mdi:lightning-bolt'
            case UnitOfElectricCurrent.AMPERE:      return 'mdi:lightning-bolt'
            case 'Ah':                              return 'mdi:lightning'
            case 'kAh':                             return 'mdi:lightning'
            case UnitOfPower.MILLIWATT:             return 'mdi:power-plug'
            case UnitOfPower.WATT:                  return 'mdi:power-plug'
            case UnitOfPower.KILO_WATT:             return 'mdi:power-plug'
            case UnitOfEnergy.WATT_HOUR:            return 'mdi:lightning'
            case UnitOfEnergy.KILO_WATT_HOUR:       return 'mdi:lightning'
            case UnitOfEnergy.MEGA_WATT_HOUR:       return 'mdi:lightning'
            case UnitOfApparentPower.VOLT_AMPERE:   return 'mdi:power-plug'
            case UnitOfFrequency.HERTZ:             return None
            case _:                                 return None
    
    
    def get_precision(self) -> int | None:
        """Convert from HA unit to number of digits displayed"""

        match self._entity.format:
            case FORMAT.INT32:
                # We can calculate the suggested precision
                weight = self._entity.weight * self._unit_weight
                if weight >= 1.0:
                    return 0
                else:
                    return math.ceil(-1*math.log10(weight))

            case FORMAT.FLOAT:
                # continue below with precision derived from unit
                pass  

            case _:
                return None
        
        match self._attr_unit:
            case UnitOfTemperature.CELSIUS:         return 1    # TEMPERATURE
            case UnitOfTemperature.FAHRENHEIT:      return 1    # TEMPERATURE
            case UnitOfTime.DAYS:                   return 0    # DURATION
            case UnitOfTime.HOURS:                  return 0    # DURATION
            case UnitOfTime.MINUTES:                return 0    # DURATION
            case UnitOfTime.SECONDS:                return 0    # DURATION
            case '%':                               return 0    # BATTERY
            case UnitOfElectricPotential.VOLT:      return 1    # VOLTAGE
            case UnitOfElectricCurrent.AMPERE:      return 1    # CURRENT
            case 'VA':                              return 3    # APPARENT_POWER
            case 'kVA':                             return 3    # APPARENT_POWER
            case UnitOfPower.MILLIWATT:             return 3    # POWER
            case UnitOfPower.WATT:                  return 3    # POWER
            case UnitOfPower.KILO_WATT:             return 3    # POWER
            case UnitOfEnergy.WATT_HOUR:            return 3    # ENERGY
            case UnitOfEnergy.KILO_WATT_HOUR:       return 3    # ENERGY
            case UnitOfEnergy.MEGA_WATT_HOUR:       return 3    # ENERGY
            case UnitOfApparentPower.VOLT_AMPERE:   return 3
            case UnitOfFrequency.HERTZ:             return 1    # FREQUENCY
            case _:                                 return 3
    
    
    def get_number_device_class(self) -> NumberDeviceClass|None:
        """Convert from HA unit to NumberDeviceClass"""
        if self._entity.format == FORMAT.SHORT_ENUM or self._entity.format == FORMAT.LONG_ENUM:
            return NumberDeviceClass.ENUM
            
        match self._attr_unit:
            case UnitOfTemperature.CELSIUS:         return NumberDeviceClass.TEMPERATURE
            case UnitOfTemperature.FAHRENHEIT:      return NumberDeviceClass.TEMPERATURE
            case UnitOfTime.DAYS:                   return NumberDeviceClass.DURATION
            case UnitOfTime.HOURS:                  return NumberDeviceClass.DURATION
            case UnitOfTime.MINUTES:                return NumberDeviceClass.DURATION
            case UnitOfTime.SECONDS:                return NumberDeviceClass.DURATION
            case '%':                               return NumberDeviceClass.BATTERY
            case UnitOfElectricPotential.VOLT:      return NumberDeviceClass.VOLTAGE
            case UnitOfElectricCurrent.AMPERE:      return NumberDeviceClass.CURRENT
            case 'VA':                              return NumberDeviceClass.APPARENT_POWER
            case 'kVA':                             return NumberDeviceClass.APPARENT_POWER
            case UnitOfPower.MILLIWATT:             return NumberDeviceClass.POWER
            case UnitOfPower.WATT:                  return NumberDeviceClass.POWER
            case UnitOfPower.KILO_WATT:             return NumberDeviceClass.POWER
            case UnitOfEnergy.WATT_HOUR:            return NumberDeviceClass.ENERGY
            case UnitOfEnergy.KILO_WATT_HOUR:       return NumberDeviceClass.ENERGY
            case UnitOfEnergy.MEGA_WATT_HOUR:       return NumberDeviceClass.ENERGY
            case UnitOfApparentPower.VOLT_AMPERE:   return None
            case UnitOfFrequency.HERTZ:             return NumberDeviceClass.FREQUENCY
            case _:                                 return None
    
    
    def get_sensor_device_class(self) -> SensorDeviceClass|None:
        """Convert from HA unit to SensorDeviceClass"""
        if self._entity.format == FORMAT.SHORT_ENUM or self._entity.format == FORMAT.LONG_ENUM:
            return SensorDeviceClass.ENUM
            
        match self._attr_unit:
            case UnitOfTemperature.CELSIUS:         return SensorDeviceClass.TEMPERATURE
            case UnitOfTemperature.FAHRENHEIT:      return SensorDeviceClass.TEMPERATURE
            case UnitOfTime.DAYS:                   return SensorDeviceClass.DURATION
            case UnitOfTime.HOURS:                  return SensorDeviceClass.DURATION
            case UnitOfTime.MINUTES:                return SensorDeviceClass.DURATION
            case UnitOfTime.SECONDS:                return SensorDeviceClass.DURATION
            case '%':                               return SensorDeviceClass.BATTERY
            case UnitOfElectricPotential.VOLT:      return SensorDeviceClass.VOLTAGE
            case UnitOfElectricCurrent.AMPERE:      return SensorDeviceClass.CURRENT
            case 'VA':                              return SensorDeviceClass.APPARENT_POWER
            case 'kVA':                             return SensorDeviceClass.APPARENT_POWER
            case UnitOfPower.MILLIWATT:             return SensorDeviceClass.POWER
            case UnitOfPower.WATT:                  return SensorDeviceClass.POWER
            case UnitOfPower.KILO_WATT:             return SensorDeviceClass.POWER
            case UnitOfEnergy.WATT_HOUR:            return SensorDeviceClass.ENERGY
            case UnitOfEnergy.KILO_WATT_HOUR:       return SensorDeviceClass.ENERGY
            case UnitOfEnergy.MEGA_WATT_HOUR:       return SensorDeviceClass.ENERGY
            case UnitOfApparentPower.VOLT_AMPERE:   return None
            case UnitOfFrequency.HERTZ:             return SensorDeviceClass.FREQUENCY
            case _:                                 return None
    
    
    def get_sensor_state_class(self) -> SensorStateClass|None:
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
        nrs_ti = [
            3078, 3081, 3083, # xt
            7007, 7008, 7011, 7012, 7013, 7017, 7018, 7019, # bsp
            11006, 11007, 11008, 11009, 11025, # vt
            15016, 15017, 15018, 15019, 15020, 15021, 15022, 15023, 15024, 15025, 15030, 15042, # vs
        ]
        
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
    
    
    def get_entity_category(self) -> EntityCategory|None:
        
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
        nrs_diag = [5012]
        if self._entity.nr in nrs_diag:
            return EntityCategory.DIAGNOSTIC
        
        # Return None for params that are a setting
        # Leads to the entities being added under 'Controls'
        if self._entity.obj_type == OBJ_TYPE.PARAMETER:
            return None
        
        # Return None for all others
        return None
    
    
    def get_number_step(self) -> list[int]|None:
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
    