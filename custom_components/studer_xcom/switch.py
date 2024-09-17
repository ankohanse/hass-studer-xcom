import asyncio
import logging
import math
from typing import Mapping

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.switch import ENTITY_ID_FORMAT
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

from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
)

from datetime import timedelta
from datetime import datetime

from collections import defaultdict
from collections import namedtuple
from collections.abc import Mapping

from .const import (
    DOMAIN,
    COORDINATOR,
    MANUFACTURER,
    SWITCH_VALUES_ON,
    SWITCH_VALUES_OFF,
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
    await helper.async_setup_entry(Platform.SWITCH, StuderSwitch, async_add_entities)


class StuderSwitch(CoordinatorEntity, SwitchEntity, StuderEntity):
    """
    Representation of a Studer Switch Entity.
    
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
        self._xcom_flash_state = None
        self._xcom_ram_state = None
        self._set_is_on = None
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
        
        value = entity.valueModified if entity.valueModified is not None else entity.value

        match entity.format:
            case FORMAT.BOOL:
                attr_val = value
                
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                attr_val = entity.options.values.get(value, value)

            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a select entity")

        if attr_val in SWITCH_VALUES_ON:
            attr_is_on = True
            attr_state = STATE_ON
            
        elif attr_val in SWITCH_VALUES_OFF:
            attr_is_on = False
            attr_state = STATE_OFF
        else:
            attr_is_on = None
            attr_state = None

        # Process any changes
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
        
        # update value if it has changed
        if is_create or self._xcom_flash_state != entity.value:
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified

        if is_create or self._attr_is_on != attr_is_on:
            self._attr_is_on = attr_is_on
            self._attr_state = attr_state
            
            self._attr_unit_of_measurement = self.get_unit()
            self._attr_icon = self.get_icon()
            changed = True
            
        return changed
    
    
    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""
        entity_map = self._coordinator.data
        entity = entity_map.get(self.object_id)

        match entity.format:
            case FORMAT.BOOL:
                data_val = 1
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                data_val = next((k for k,v in entity.options.items() if k in SWITCH_VALUES_ON or v in SWITCH_VALUES_ON), None)
            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a select entity")
                data_val = None
                
        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to ON ({data_val})")
            
            success = await self._coordinator.async_modify_data(entity, data_val)
            if success:
                self._attr_is_on = True
                self._attr_state = STATE_ON
                self._xcom_ram_state = data_val
                self.async_write_ha_state()
    
    
    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""
        entity_map = self._coordinator.data
        entity = entity_map.get(self.object_id)

        match entity.format:
            case FORMAT.BOOL:
                data_val = 0
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                data_val = next((k for k,v in entity.options.items() if k in SWITCH_VALUES_OFF or v in SWITCH_VALUES_OFF), None)
            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a select entity")
                data_val = None

        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to OFF ({data_val})")
            
            success = await self._coordinator.async_modify_data(entity, data_val)
            if success:
                self._attr_is_on = False
                self._attr_state = STATE_OFF
                self._xcom_ram_state = data_val
                self.async_write_ha_state()
    
