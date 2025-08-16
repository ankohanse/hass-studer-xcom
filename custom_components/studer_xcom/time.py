import logging

from homeassistant.components.time import TimeEntity
from homeassistant.components.time import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from datetime import time

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
    await helper.async_setup_entry(Platform.TIME, StuderTime, async_add_entities)


class StuderTime(CoordinatorEntity, TimeEntity, StuderEntity):
    """
    Representation of a Studer Time Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.TIME)
        
        # The unique identifier for this sensor within Home Assistant
        self.entity_id: str = ENTITY_ID_FORMAT.format(entity.object_id)

        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_entity_category = self.get_entity_category()
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
        
        value = entity.valueModified if entity.valueModified is not None else entity.value

        match entity.format:
            case FORMAT.INT32:
                # Studer entity value is minutes since midnight with values between 0 (00:00) and 1440 (24:00).
                # TimeEntity expects time object and can only be between 00:00 and 23:59
                # We sneakily replace value 1440 (24:00) into 23:59
                if value is None: 
                    attr_val = None
                elif int(value) >= 1440:
                    attr_val = time(23, 59).replace(tzinfo=self._coordinator.time_zone)
                else:
                    attr_val = time(int(value // 60), int(value % 60)).replace(tzinfo=self._coordinator.time_zone)

            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a time entity")
                return
        
        # update value if it has changed
        changed = False
        
        if force or (self._xcom_flash_state != entity.value):
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified
        
        if force or (self._attr_native_value != attr_val):
            self._attr_state = attr_val
            self._attr_native_value = attr_val

            self._attr_icon = self.get_icon()
            changed = True

        return changed    
    
    
    async def async_set_value(self, value: time) -> None:
        """Change the date/time"""
        
        entity_map: dict[str, StuderEntityData] = self._coordinator.data
        entity: StuderEntityData = entity_map.get(self.object_id)

        match entity.format:
            case FORMAT.INT32:
                # TimeEntity is a time object and can only be between 00:00 and 23:59
                # Studer entity value is minutes since midnight with values between 0 (00:00) and 1440 (24:00).
                
                minutes = value.hour * 60 + value.minute
                if minutes < 1439:
                    entity_value = minutes
                    trace_value = value
                else:
                    # We sneakily replace input 23:59 into 1440 (24:00)
                    entity_value = 1440
                    trace_value = "24:00"

            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a time entity")
                return
        
        _LOGGER.debug(f"Set {self.entity_id} to {trace_value} ({entity_value})")

        success = await self._coordinator.async_modify_data(entity, entity_value)
        if success:
            self._attr_native_value = value
            self._xcom_ram_state = entity_value
            self.async_write_ha_state()

            # No need to update self._xcom_ram_state for this entity

