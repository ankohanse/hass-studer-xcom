import asyncio
import logging
import math

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.select import SelectEntity
from homeassistant.components.select import ENTITY_ID_FORMAT
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

from datetime import timedelta
from datetime import datetime

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
    Setting up the adding and updating of select entities
    """
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
    await helper.async_setup_entry(Platform.SELECT, StuderSelect, async_add_entities)


class StuderSelect(CoordinatorEntity, SelectEntity, StuderEntity):
    """
    Representation of a Studer Select Entity.
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.SELECT)
        
        # The unique identifier for this sensor within Home Assistant
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)

        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_options = list(entity.options.values())
        
        self._attr_entity_category = self.get_entity_category()
        self._attr_device_class = None
        
        self._attr_device_info = DeviceInfo( identifiers = {(DOMAIN, entity.device_id)}, )

        # Update value
        self._update_value(entity, True)
    
    
    async def async_added_to_hass(self) -> None:
        """
        Handle when the entity has been added
        """
        await super().async_added_to_hass()

        # Get last data from previous HA run                      
        last_state = await self.async_get_last_state()
        if last_state:
            try:
                if last_state.state in self._attr_options:
                    _LOGGER.debug(f"Restore entity '{self.entity_id}' value to {last_state.state}")
            
                    self._attr_current_option = last_state.state
            except:
                pass

        last_extra = await self.async_get_last_extra_data()
        if last_extra:
            dict_extra = last_extra.as_dict()
            self._xcom_flash_state = dict_extra.get(ATTR_XCOM_FLASH_STATE)
            self._xcom_ram_state = dict_extra.get(ATTR_XCOM_RAM_STATE)
    
    
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
       
        if entity.format != FORMAT.SHORT_ENUM and entity.format != FORMAT.LONG_ENUM:
            _LOGGER.error(f"Unexpected format ({entity.format}) for a select entity")

        value = entity.valueModified if entity.valueModified is not None else entity.value

        attr_val = entity.options.get(str(value), value) if value!=None else None

        # update value if it has changed
        changed = False
        
        if force or (self._xcom_flash_state != entity.value):
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified

        if force or (self._attr_current_option != attr_val):
            self._attr_current_option = attr_val

            self._attr_unit_of_measurement = self.get_unit()
            self._attr_icon = self.get_icon()
            changed = True

        return changed
    
    
    async def async_select_option(self, option: str) -> None:
        """Change the selected option"""
        entity_map = self._coordinator.data
        entity = entity_map.get(self.object_id)

        data_val = next((k for k,v in entity.options.items() if v == option), None)
        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to {option} ({data_val})")
                
            success = await self._coordinator.async_modify_data(entity, data_val)
            if success:
                self._attr_current_option = option
                self._xcom_ram_state = option
                self.async_write_ha_state()
    
    