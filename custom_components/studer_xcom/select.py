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
from .entity_base import (
    StuderEntityHelperFactory,
    StuderEntityHelper,
    StuderEntity,
)
from aioxcom import (
    FORMAT,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of select entities
    """
    helper = StuderEntityHelperFactory.create(hass, config_entry)
    await helper.async_setup_entry(Platform.SELECT, StuderSelect, async_add_entities)


class StuderSelect(CoordinatorEntity, SelectEntity, StuderEntity):
    """
    Representation of a Studer Select Entity.
    """
    
    def __init__(self, coordinator, install_id, entity) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity)
        
        # The unique identifier for this sensor within Home Assistant
        self.object_id = entity.object_id
        self.entity_id = ENTITY_ID_FORMAT.format(entity.unique_id)
        self.install_id = install_id
        
        self._coordinator = coordinator

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_flash_state = None
        self._xcom_ram_state = None
        self._set_state = None

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
        
        entity_map = self._coordinator.data
        
        # find the correct device and status corresponding to this sensor
        entity = entity_map.get(self.object_id)

        # Update any attributes
        if entity:
            if self._update_attributes(entity, False):
                self.async_write_ha_state()
    
    
    def _update_attributes(self, entity, is_create):
        
        if entity.format != FORMAT.SHORT_ENUM and entity.format != FORMAT.LONG_ENUM:
            _LOGGER.error(f"Unexpected format ({entity.format}) for a select entity")

        # Process any changes
        changed = False
        value = entity.valueModified if entity.valueModified is not None else entity.value

        attr_val = entity.options.get(str(value), value) if value!=None else None

        # update creation-time only attributes
        if is_create:
            self._attr_unique_id = entity.unique_id
            
            self._attr_has_entity_name = True
            self._attr_name = entity.name
            self._name = entity.name
            
            self._attr_options = list(entity.options.values())
            
            self._attr_entity_category = self.get_entity_category()
            self._attr_device_class = None
            
            self._attr_device_info = DeviceInfo(
               identifiers = {(DOMAIN, entity.device_id)},
            )
            changed = True
        
        # update value if it has changed
        if is_create or self._xcom_flash_state != entity.value:
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified

        if is_create or self._attr_current_option != attr_val:
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
    
    