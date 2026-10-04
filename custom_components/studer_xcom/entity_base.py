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
from homeassistant.const import REVOLUTIONS_PER_MINUTE
from homeassistant.const import UnitOfApparentPower
from homeassistant.const import UnitOfDataRate
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.const import UnitOfElectricPotential
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfFrequency
from homeassistant.const import UnitOfInformation
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfReactivePower
from homeassistant.const import UnitOfTemperature
from homeassistant.const import UnitOfTime
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from pystudershared import StuderAccess, StuderDataType, StuderUserLevel

from .const import (
    ATTR_STUDER_FLASH_STATE,
    ATTR_STUDER_RAM_STATE,
    ATTR_STUDER_STATE,
    ATTR_STORED_VALUE,
    ATTR_STORED_VALUE_MODIFIED,
    PRODUCTS,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class UI():
    u: str    # Home Assistant unit
    w: int    # weight
    p: int    # precision
    i: str    # icon
    ndc: str  # NumberDeviceClass
    sdc: str  # SensorDeviceClass

DEFAULT_UNIT_INFO = UI(u=None, w=1, p=1, i=None, ndc=None, sdc=None)

UNIT_INFO: dict[str,UI] = {
    '°C':           UI(u=UnitOfTemperature.CELSIUS ,                w=1,    p=1, i='mdi:thermometer',    ndc=NumberDeviceClass.TEMPERATURE,     sdc=SensorDeviceClass.TEMPERATURE),
    '°F':           UI(u=UnitOfTemperature.FAHRENHEIT,              w=1,    p=1, i='mdi:thermometer',    ndc=NumberDeviceClass.TEMPERATURE,     sdc=SensorDeviceClass.TEMPERATURE),
    'days':         UI(u=UnitOfTime.DAYS,                           w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'h':            UI(u=UnitOfTime.HOURS,                          w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'hours':        UI(u=UnitOfTime.HOURS,                          w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'min':          UI(u=UnitOfTime.MINUTES,                        w=1,    p=0, i='mdi:timer-sand',     ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'minutes':      UI(u=UnitOfTime.MINUTES,                        w=1,    p=0, i='mdi:timer-sand',     ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'Minutes':      UI(u=UnitOfTime.MINUTES,                        w=1,    p=0, i='mdi:timer-sand',     ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    's':            UI(u=UnitOfTime.SECONDS,                        w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    's.':           UI(u=UnitOfTime.SECONDS,                        w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'sec':          UI(u=UnitOfTime.SECONDS,                        w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'seconds':      UI(u=UnitOfTime.SECONDS,                        w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    'Seconds':      UI(u=None,                                      w=1,    p=0, i='mdi:clock',          ndc=None,                              sdc=SensorDeviceClass.TIMESTAMP),
    'ms':           UI(u=UnitOfTime.MILLISECONDS,                   w=1,    p=0, i='mdi:timer',          ndc=NumberDeviceClass.DURATION,        sdc=SensorDeviceClass.DURATION),
    '%':            UI(u=PERCENTAGE,                                w=1,    p=0, i='mdi:percent',        ndc=None,                              sdc=None),
    '% SOC':        UI(u=PERCENTAGE,                                w=1,    p=0, i='mdi:percent',        ndc=NumberDeviceClass.BATTERY,         sdc=SensorDeviceClass.BATTERY),
    '%/s':          UI(u='%/s',                                     w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '%/min':        UI(u='%/min',                                   w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '%/day':        UI(u='%/day',                                   w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '%Cnom/month':  UI(u='%Cnom/month',                             w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '‰':            UI(u='‰',                                       w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'V':            UI(u=UnitOfElectricPotential.VOLT,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.VOLTAGE,         sdc=SensorDeviceClass.VOLTAGE),
    'Vac':          UI(u=UnitOfElectricPotential.VOLT,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.VOLTAGE,         sdc=SensorDeviceClass.VOLTAGE),
    'Vdc':          UI(u=UnitOfElectricPotential.VOLT,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.VOLTAGE,         sdc=SensorDeviceClass.VOLTAGE),
    'V/°C':         UI(u='V/°C',                                    w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'A':            UI(u=UnitOfElectricCurrent.AMPERE,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.CURRENT,         sdc=SensorDeviceClass.CURRENT),
    'Aac':          UI(u=UnitOfElectricCurrent.AMPERE,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.CURRENT,         sdc=SensorDeviceClass.CURRENT),
    'Adc':          UI(u=UnitOfElectricCurrent.AMPERE,              w=1,    p=1, i='mdi:lightning-bolt', ndc=NumberDeviceClass.CURRENT,         sdc=SensorDeviceClass.CURRENT),
    'Ah':           UI(u='Ah',                                      w=1,    p=1, i='mdi:lightning-bolt', ndc=None,                              sdc=None),
    'kAh':          UI(u='kAh',                                     w=1,    p=1, i='mdi:lightning-bolt', ndc=None,                              sdc=None),
    'A/%':          UI(u='A/%',                                     w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'mW':           UI(u=UnitOfPower.MILLIWATT,                     w=1,    p=1, i='mdi:power-plug',     ndc=NumberDeviceClass.POWER,           sdc=SensorDeviceClass.POWER),
    'W':            UI(u=UnitOfPower.WATT,                          w=1,    p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.POWER,           sdc=SensorDeviceClass.POWER),
    'kW':           UI(u=UnitOfPower.KILO_WATT,                     w=1,    p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.POWER,           sdc=SensorDeviceClass.POWER),
    'Wh':           UI(u=UnitOfEnergy.WATT_HOUR,                    w=1,    p=3, i='mdi:lightning-bolt', ndc=NumberDeviceClass.ENERGY,          sdc=SensorDeviceClass.ENERGY),
    'kWh':          UI(u=UnitOfEnergy.KILO_WATT_HOUR,               w=1,    p=3, i='mdi:lightning-bolt', ndc=NumberDeviceClass.ENERGY,          sdc=SensorDeviceClass.ENERGY),
    'MWh':          UI(u=UnitOfEnergy.MEGA_WATT_HOUR,               w=1,    p=3, i='mdi:lightning-bolt', ndc=NumberDeviceClass.ENERGY,          sdc=SensorDeviceClass.ENERGY),
    'VA':           UI(u=UnitOfApparentPower.VOLT_AMPERE,           w=1,    p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.APPARENT_POWER,  sdc=SensorDeviceClass.APPARENT_POWER),
    'kVA':          UI(u=UnitOfApparentPower.VOLT_AMPERE,           w=1000, p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.APPARENT_POWER,  sdc=SensorDeviceClass.APPARENT_POWER),
    'VAR':          UI(u=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,  w=1,    p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.REACTIVE_POWER,  sdc=SensorDeviceClass.REACTIVE_POWER),
    'VAr':          UI(u=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,  w=1,    p=3, i='mdi:power-plug',     ndc=NumberDeviceClass.REACTIVE_POWER,  sdc=SensorDeviceClass.REACTIVE_POWER),
    'Hz':           UI(u=UnitOfFrequency.HERTZ,                     w=1,    p=1, i=None,                 ndc=NumberDeviceClass.FREQUENCY,       sdc=SensorDeviceClass.FREQUENCY),
    'Hz/s':         UI(u='Hz/s',                                    w=1,    p=1, i=None,                 ndc=None,                              sdc=None),     
    'mHz/s':        UI(u='mHz/s',                                   w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'RPM':          UI(u=REVOLUTIONS_PER_MINUTE,                    w=1,    p=0, i=None,                 ndc=None,                              sdc=None),
    'KiB':          UI(u=UnitOfInformation.KIBIBYTES,               w=1,    p=0, i=None,                 ndc=NumberDeviceClass.DATA_SIZE,       sdc=SensorDeviceClass.DATA_SIZE),
    'kbps':         UI(u=UnitOfDataRate.KILOBYTES_PER_SECOND,       w=1,    p=0, i=None,                 ndc=NumberDeviceClass.DATA_RATE,       sdc=SensorDeviceClass.DATA_RATE),
    'degree':       UI(u='degree',                                  w=1,    p=0, i=None,                 ndc=None,                              sdc=None),
    '°':            UI(u='°',                                       w=1,    p=0, i=None,                 ndc=None,                              sdc=None),
    '/20':          UI(u='/20',                                     w=1,    p=0, i=None,                 ndc=None,                              sdc=None),
    'Ctmp':         UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'Cdyn':         UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'addr':         UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'Level':        UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '-':            UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    '':             UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    'None':         UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
    None:           UI(u=None,                                      w=1,    p=1, i=None,                 ndc=None,                              sdc=None),
}


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

        self.object_id: str = entity.object_id

        # Attributes from Entity base class
        self._attr_unique_id = entity.unique_id
        self._attr_has_entity_name = True
        self._attr_name = entity.datapoint.name
        self._name = entity.datapoint.name

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._studer_state: Any = None
        self._studer_flash_state: Any = None
        self._studer_ram_state: Any = None

        # Attributes derived from Unit
        unit_info = UNIT_INFO.get(self._entity.datapoint.unit)
        if unit_info is None:
            _LOGGER.warning(f"Encountered a unit or measurement '{self._entity.datapoint.unit}' for '{self._entity.unique_id}' that may not be supported by Home Assistant. Please contact the integration developer to have this resolved.")
            unit_info = DEFAULT_UNIT_INFO

        self._attr_icon = unit_info.i
        self._attr_unit = unit_info.u
        self._unit_weight = unit_info.w
        self._unit_precision = unit_info.p
        self._unit_ndc = unit_info.ndc # NumberDeviceClass
        self._unit_sdc = unit_info.sdc # SensorDeviceClass


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
        if self._studer_state is not None:
            self._attributes[ATTR_STUDER_STATE] = self._studer_state

        if self._studer_flash_state is not None:
            self._attributes[ATTR_STUDER_FLASH_STATE] = self._studer_flash_state

        if self._studer_ram_state is not None:
            self._attributes[ATTR_STUDER_RAM_STATE] = self._studer_ram_state

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

            # Update using the entity value
            self._update_value(force=True)
    

    def _update_value(self, force:bool=False):
        """
        Process any changes in value
        
        To be extended by derived entities
        """


    def get_unit(self) -> str|None:
        """
        Convert from Studer datapoint unit of measurement to HA unit of measurement
        """
        return self._attr_unit
        
    
    def get_precision(self) -> int | None:
        """
        Convert from Studer datapoint to number of digits displayed
        """

        match self._entity.datapoint.data_type:
            case StuderDataType.INT16 | StuderDataType.INT32 | StuderDataType.INT64 | \
                 StuderDataType.UINT16 | StuderDataType.UINT32 | StuderDataType.UINT64:
                
                # We can calculate the suggested precision
                weight = self._entity.weight * self._unit_weight
                if weight >= 1.0:
                    return 0
                else:
                    return math.ceil(-1*math.log10(weight))

            case StuderDataType.FLOAT32 | StuderDataType.FLOAT64:
                # Use precision derived from unit of measurement
                return self._unit_precision

            case _:
                return None


    def get_number_device_class(self) -> NumberDeviceClass|None:
        """
        Convert from Studer datapoint to NumberDeviceClass
        """
        if self._entity.datapoint.data_type in [StuderDataType.ENUM16, StuderDataType.ENUM32]:
            return NumberDeviceClass.ENUM
        else:
            # Number device class is derived from the unit of measurement
            return self._unit_ndc
    
    
    def get_sensor_device_class(self) -> SensorDeviceClass|None:
        """
        Convert from from Studer datapoint to SensorDeviceClass
        """
        if self._entity.datapoint.data_type in [StuderDataType.ENUM16, StuderDataType.ENUM32]:
            return SensorDeviceClass.ENUM
        else:
            # Sensor device class is derived from the unit of measurement
            return self._unit_sdc


    def get_sensor_state_class(self) -> SensorStateClass|None:
        """
        Convert from Studer datapoint to SensorStateClass
        """
        # Return StateClass=None for Enum or Label
        if self._entity.datapoint.data_type in [StuderDataType.ENUM16, StuderDataType.ENUM32, StuderDataType.BITFIELD, StuderDataType.STRING]:
            return None
        
        # Return StateClass=None for params that are a setting, unlikely to change often
        if self._entity.datapoint.access in [StuderAccess.READ_WRITE, StuderAccess.WRITE] and \
           self._entity.datapoint.userlevel_w > StuderUserLevel.VIEWONLY and \
           self._entity.datapoint.userlevel_w <= StuderUserLevel.EXPERT:
            
            return None
        
        # Return StateClass=None, Total or Total_Increasing for some specific entities
        PRODUCTS_NRS_NONE = {
            PRODUCTS.XCOM: {
                'xcom': [99022]
            },
            PRODUCTS.NEXT: {
            },
        }
        PRODUCTS_NRS_T = {
            PRODUCTS.XCOM: {
            },
            PRODUCTS.NEXT: {
            },
        }
        PRODUCTS_NRS_TI = {
            PRODUCTS.XCOM: {
                'xt':  [3078, 3081, 3083],
                'bsp': [7007, 7008, 7011, 7012, 7013, 7017, 7018, 7019],
                'vt':  [11006, 11007, 11008, 11009, 11025],
                'vs':  [15016, 15017, 15018, 15019, 15020, 15021, 15022, 15023, 15024, 15025, 15030, 15042],
            },
            PRODUCTS.NEXT: {
                'acs': [16, 20, 24, 28, 32, 36, 40, 42, 328, 332, 336, 340, 344, 348, 628, 632, 636, 640, 644, 648, 928, 932, 936, 940, 944, 948 ],
                'bat': [2, 6, 10, 14, 18, 22],
                'flx': [16, 20, 24, 28, 32, 36, 40, 42, 328, 332, 336, 340, 344, 348, 628, 632, 636, 640, 644, 648, 928, 932, 936, 940, 944, 948 ],
                'nx1': [1805, 7811, 7815, 7819],
                'nx3': [4205, 5711, 5715, 5719, 6011, 6015, 6019, 6311, 6315, 6319, 12311, 12315, 12319],
                'nxg': [905],
                'sys': [3916, 3920, 2934, 3928, 3932, 3926, 3940, 3942, 4228, 4232, 4236, 4240, 4244, 4248, 4528, 4532, 4536, 4540, 4544, 4548, 4828, 4832, 4836, 4840, 4844, 4848, 5116, 5120, 5124, 5128, 5132, 5136, 5140, 5142, 5416, 5420, 5424, 5428, 5432, 5436, 5440, 5442, 5716, 5720, 5724, 5728, 5732, 5736, 5740, 5742, 6016, 6020, 6024, 6028, 6032, 6036, 6040, 6042, 6316, 6320, 6324, 6328, 6332, 6336, 6340, 6342, 6628, 6632, 6636, 6640, 6644, 6648, 6928, 6932, 6936, 6940, 6944, 6948, 7228, 7232, 7236, 7240, 7244, 7248, 7511, 7515, 7519, 8402, 8406, 8410, 8414, 8418, 8422]
            }
        }
        nrs_none = PRODUCTS_NRS_NONE.get(self._coordinator.product, {}).get(self._entity.datapoint.family_id, [])
        nrs_t    = PRODUCTS_NRS_T.get(   self._coordinator.product, {}).get(self._entity.datapoint.family_id, [])
        nrs_ti   = PRODUCTS_NRS_TI.get(  self._coordinator.product, {}).get(self._entity.datapoint.family_id, [])

        if self._entity.datapoint.nr in nrs_none:
            return None

        if self._entity.datapoint.nr in nrs_t:
            return SensorStateClass.TOTAL
            
        elif self._entity.datapoint.nr in nrs_ti:
            return SensorStateClass.TOTAL_INCREASING

        # Return StateClass=None depending on sensor device-class
        sdc_none = [SensorDeviceClass.ENERGY, SensorDeviceClass.TIMESTAMP]
        if self.get_sensor_device_class() in sdc_none:
            return None

        # All other cases: StateClass=measurement            
        return SensorStateClass.MEASUREMENT
    
    
    def get_entity_category(self) -> EntityCategory|None:
        """
        Convert from Studer datapoint to EntityCategory (Config, Diagnostics, None)
        """
        
        # Return None for params that are a setting
        # Leads to the entities being added under 'Controls'
        if self._entity.datapoint.access in [StuderAccess.READ_WRITE, StuderAccess.WRITE] and \
           self._entity.datapoint.userlevel_w > StuderUserLevel.VIEWONLY and \
           self._entity.datapoint.userlevel_w <= StuderUserLevel.EXPERT:

            return None
        
        # Return CONFIG for some specific entries we want added under 'Configuration'
        # Typically intended for restart or update functionality
        PRODUCTS_NRS_CONFIG= {
            PRODUCTS.XCOM: [],
            PRODUCTS.NEXT: [],
        }

        # Return DIAGNOSTIC for some specific entries we want added under 'Diagnostic'
        PRODUCTS_NRS_DIAGNOSTICS= {
            PRODUCTS.XCOM: [5012], # UserLevel
            PRODUCTS.NEXT: [],
        }

        nrs_config = PRODUCTS_NRS_CONFIG.get(self._coordinator.product, [])
        if self._entity.datapoint.nr in nrs_config:
            return EntityCategory.CONFIG
            
        nrs_diagnostics = PRODUCTS_NRS_DIAGNOSTICS.get(self._coordinator.product, [])
        if self._entity.datapoint.nr in nrs_diagnostics:
            return EntityCategory.DIAGNOSTIC
        
        # Return None for all others
        return None
    
    
    def get_number_step(self) -> list[int]|None:
        """
        Return a suggested step size for number entity inputs based on the Studer datapoint
        """
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
        if self._entity.datapoint.min is not None and self._entity.datapoint.max is not None:
            min = int(self._entity.datapoint.min)
            max = int(self._entity.datapoint.max)
            diff = max - min
            
            for c in candidates:
                if (min % c == 0) and (max % c == 0) and (diff % c == 0):
                    return c
                
        return None
    