import logging
import math

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
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


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of sensor entities
    """
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
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
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)

        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_state_class = self.get_sensor_state_class()
        self._attr_entity_category = self.get_entity_category()
        self._attr_device_class = self.get_sensor_device_class() 

        self._attr_device_info = DeviceInfo( identifiers = {(DOMAIN, entity.device_id)}, )

        # Create all attributes (but with unknown value).
        # After this constructor ends, base class StuderEntity.async_added_to_hass() will 
        # set the value using the restored value from the last HA run.
        self._update_value(force=True)
        

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        
        # Update value
        if self._update_value():
            self.async_write_ha_state()
    
    
    def _update_value(self, force:bool=False):
        """Process any changes in value"""
        
        # Transform values according to the metadata params for this status/sensor
        match self._entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                attr_precision = self.get_precision()
                attr_digits = 3
                attr_val = round(float(self._entity.value) * weight, attr_digits) if self._entity.value!=None and not math.isnan(self._entity.value) else None
                attr_unit = self.get_unit()

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                attr_precision = self.get_precision()
                attr_val = int(self._entity.value) * weight if self._entity.value!=None and not math.isnan(self._entity.value) else None
                attr_unit = self.get_unit()
                    
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                # Lookup the dict string for the value and otherwise return the value itself
                weight = None
                attr_precision = None
                attr_val = self._entity.options.get(str(self._entity.value), self._entity.value) if self._entity.value!=None and not math.isnan(self._entity.value) else None
                attr_unit = None

            case _:
                _LOGGER.warning(f"Unexpected entity format ({self._entity.format}) for a sensor")
                return
        
        # update value if it has changed
        changed = False

        if force or (self._xcom_state != self._entity.value):
            self._xcom_state = self._entity.value
            changed = True
        
        if force or (self._attr_native_value != attr_val):
            if not force:
                _LOGGER.debug(f"Sensor change value {self.object_id} from {self._attr_native_value} to {attr_val}")

            self._attr_state = attr_val
            self._attr_native_value = attr_val
            self._attr_native_unit_of_measurement = attr_unit
            self._attr_suggested_display_precision = attr_precision
            
            self._attr_icon = self.get_icon()
            changed = True
        
        return changed
    
