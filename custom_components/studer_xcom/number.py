import asyncio
import logging
import math

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.number import NumberEntity
from homeassistant.components.number import NumberMode
from homeassistant.components.number import ENTITY_ID_FORMAT
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
        self.object_id = entity.object_id
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)
        self._attr_unique_id = entity.unique_id
        
        # Standard HA entity attributes
        self._attr_has_entity_name = True
        self._attr_name = entity.name
        self._name = entity.name
        
        self._attr_mode = NumberMode.BOX
        self._attr_device_class = self.get_number_device_class()
        self._attr_entity_category = self.get_entity_category()
        
        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, entity.device_id)},
        )

        # Custom extra attributes for the entity
        self._attributes: dict[str, str | list[str]] = {}
        self._xcom_flash_state = None
        self._xcom_ram_state = None

        # Update value
        self._update_value(entity, True)
    
    
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
        
        # find the correct device and status corresponding to this sensor
        entity: StuderEntityData|None = self._coordinator.data.get(self.object_id)
        if entity:
            # Update value
            if self._update_value(entity, False):
                self.async_write_ha_state()
    
    
    def _update_value(self, entity: StuderEntityData, force:bool=False):
        """Process any changes in value"""
        
        value = entity.valueModified if entity.valueModified is not None else entity.value

        match entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                attr_precision = 3
                attr_digits = 3
                attr_min = float(entity.min) * weight if entity.min is not None else None
                attr_max = float(entity.max) * weight if entity.max is not None else None
                attr_val = round(float(value) * weight, attr_digits) if value is not None and not math.isnan(value) else None
                attr_step = entity.inc

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                attr_precision = None
                attr_min = int(entity.min) * weight if entity.min is not None else None
                attr_max = int(entity.max) * weight if entity.max is not None else None
                attr_val = int(value) * weight if value is not None and not math.isnan(value) else None
                attr_step = self.get_number_step()

            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a number entity")
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
        
        if force or (self._xcom_flash_state != entity.value):
            self._xcom_flash_state = entity.value
            self._xcom_ram_state = entity.valueModified

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
        
        entity_map = self._coordinator.data
        entity = entity_map.get(self.object_id)

        match entity.format:
            case FORMAT.FLOAT:
                # Convert to float
                weight = self._entity.weight * self._unit_weight
                entity_value = float(value / weight)

            case FORMAT.INT32:
                # Convert to int
                weight = self._entity.weight * self._unit_weight
                entity_value = int(value / weight)

            case _:
                _LOGGER.error(f"Unexpected format ({entity.format}) for a number entity")
                return
        
        _LOGGER.debug(f"Set {self.entity_id} to {value} {self._attr_unit or ""} ({entity_value})")

        success = await self._coordinator.async_modify_data(entity, entity_value)
        if success:
            self._attr_native_value = value
            self._xcom_ram_state = entity_value
            self.async_write_ha_state()

