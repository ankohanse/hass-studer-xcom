import asyncio
import logging
import math

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.time import TimeEntity
from homeassistant.components.time import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from datetime import time, timedelta

from collections import defaultdict
from collections import namedtuple
from collections.abc import Mapping


from .const import (
    DOMAIN,
    COORDINATOR,
    MANUFACTURER,
    ATTR_XCOM_FLASH_STATE,
    ATTR_XCOM_RAM_STATE,
)
from .coordinator import (
    StuderCoordinator,
    StuderEntityData,
)
from .entity_base import (
    StuderEntityHelperFactory,
    StuderEntityHelper,
    StuderEntity,
)
from aioxcom import (
    FORMAT
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of number entities
    """
    helper = StuderEntityHelperFactory.create(hass, config_entry)
    await helper.async_setup_entry(Platform.TIME, StuderTime, async_add_entities)


class StuderTime(CoordinatorEntity, TimeEntity, StuderEntity):
    """
    Representation of a Studer Time Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, install_id, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity)
        
        # The unique identifier for this sensor within Home Assistant
        self.object_id: str = entity.object_id
        self.entity_id: str = ENTITY_ID_FORMAT.format(entity.unique_id)
        self.install_id: str = install_id
        
        self._coordinator: StuderCoordinator = coordinator

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_flash_state: str = None
        self._xcom_ram_state: str = None

        # Create all attributes
        self._update_attributes(entity, True)
    
    
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
        if self._xcom_flash_state:
            self._attributes[ATTR_XCOM_FLASH_STATE] = self._xcom_flash_state
        if self._xcom_ram_state:
            self._attributes[ATTR_XCOM_RAM_STATE] = self._xcom_ram_state

        return self._attributes        
    

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        
        entity_map: dict[str, StuderEntityData] = self._coordinator.data
        
        # find the correct device and status corresponding to this sensor
        status: StuderEntityData|None = entity_map.get(self.object_id)

        # Update any attributes
        if status:
            if self._update_attributes(status, False):
                self.async_write_ha_state()
    
    
    def _update_attributes(self, entity: StuderEntityData, is_create: bool):
        
        # Process any changes
        changed = False
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
        
        # update creation-time only attributes
        if is_create:
            self._attr_unique_id = entity.unique_id
            
            self._attr_has_entity_name = True
            self._attr_name = entity.name
            self._name = entity.name
            
            #self._attr_device_class = self.get_number_device_class()
            self._attr_entity_category = self.get_entity_category()
            
            self._attr_device_info = DeviceInfo(
               identifiers = {(DOMAIN, entity.device_id)},
            )
            changed = True
        
        # update value if it has changed
        if is_create or self._xcom_flash_state != entity.value:
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified
        
        if is_create or self._attr_native_value != attr_val:
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

