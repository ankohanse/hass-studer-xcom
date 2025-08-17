import logging
import math

from homeassistant.components.number import NumberEntity
from homeassistant.components.number import NumberMode
from homeassistant.components.number import ENTITY_ID_FORMAT
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
    FORMAT
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of number entities
    """
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
    await helper.async_setup_entry(Platform.NUMBER, StuderNumber, async_add_entities)


class StuderNumber(CoordinatorEntity, NumberEntity, StuderEntity):
    """
    Representation of a Studer Number Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.NUMBER)
        
        # The unique identifier for this sensor within Home Assistant
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)
        
        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_mode = NumberMode.BOX
        self._attr_device_class = self.get_number_device_class()
        self._attr_entity_category = self.get_entity_category()
        
        self._attr_device_info = DeviceInfo( identifiers = {(DOMAIN, entity.device_id)}, )

        # Create all attributes (but with unknown value).
        # After this constructor ends, base class StuderEntity.async_added_to_hass() will 
        # set the value using the restored value from the last HA run.
        self._update_value(True)
    
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        
        # Update value
        if self._update_value(False):
            self.async_write_ha_state()
    
    
    def _update_value(self, force:bool=False):
        """Process any changes in value"""
        
        value = self._entity.valueModified if self._entity.valueModified is not None else self._entity.value

        match self._entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                attr_precision = 3
                attr_digits = 3
                attr_min = float(self._entity.min) * weight if self._entity.min is not None else None
                attr_max = float(self._entity.max) * weight if self._entity.max is not None else None
                attr_val = round(float(value) * weight, attr_digits) if value is not None and not math.isnan(value) else None
                attr_step = self._entity.inc

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                attr_precision = None
                attr_min = int(self._entity.min) * weight if self._entity.min is not None else None
                attr_max = int(self._entity.max) * weight if self._entity.max is not None else None
                attr_val = int(value) * weight if value is not None and not math.isnan(value) else None
                attr_step = self.get_number_step()

            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a number entity")
                return
        
        # update creation-time only attributes
        if force:
            if attr_min:
                self._attr_native_min_value = attr_min
            if attr_max:
                self._attr_native_max_value = attr_max
            self._attr_native_step = attr_step
        
        # update value if it has changed
        changed = False
        
        if force or (self._xcom_flash_state != self._entity.value):
            self._xcom_flash_state = self._entity.value
            self._xcom_ram_state = self._entity.valueModified

        if force or (self._attr_native_value != attr_val):
            self._attr_state = attr_val
            self._attr_native_value = attr_val
            self._attr_native_unit_of_measurement = self.get_unit()
            self._attr_suggested_display_precision = attr_precision

            self._attr_icon = self.get_icon()
            changed = True

        return changed    
    
    
    async def async_set_native_value(self, value: float) -> None:
        """Change the selected option"""
        
        match self._entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                entity_value = float(value / weight)

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                entity_value = int(value / weight)

            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a number entity")
                return
        
        _LOGGER.debug(f"Set {self.entity_id} to {value} {self._attr_unit or ""} ({entity_value})")

        success = await self._coordinator.async_modify_data(self._entity, entity_value)
        if success:
            self._attr_native_value = value
            self._xcom_ram_state = entity_value
            self.async_write_ha_state()

