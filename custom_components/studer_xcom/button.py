import asyncio
import logging
import math
from typing import Mapping

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.button import ButtonEntity
from homeassistant.components.button import ENTITY_ID_FORMAT
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
    await helper.async_setup_entry(Platform.BUTTON, StuderButton, async_add_entities)


class StuderButton(CoordinatorEntity, ButtonEntity, StuderEntity):
    """
    Representation of a Studer Button Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
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
        self._xcom_state = None
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
        
        changed = False
        
        # update creation-time only attributes
        if is_create:
            self._attr_unique_id = entity.unique_id

            self._attr_has_entity_name = True
            self._attr_name = entity.name
            self._name = entity.name
            
            self._attr_entity_category = self.get_entity_category()
            self._attr_device_class = None

            self._attr_device_info = DeviceInfo(
               identifiers = {(DOMAIN, entity.device_id)},
            )
            changed = True
        
        return changed
    

    async def async_press(self) -> None:
        """Press the button."""
        entity_map = self._coordinator.data
        entity = entity_map.get(self.object_id)

        data_val = 1
        _LOGGER.info(f"Set {self.entity_id} to Signal ({data_val})")
            
        success = await self._coordinator.async_modify_data(entity, data_val)
        if success:
            self.async_write_ha_state()
