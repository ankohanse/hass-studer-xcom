import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.switch import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.const import (
    STATE_ON,
    STATE_OFF,
)

from .const import (
    DOMAIN,
    SWITCH_VALUES_ON,
    SWITCH_VALUES_OFF,
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
    await helper.async_setup_entry(Platform.SWITCH, StuderSwitch, async_add_entities)


class StuderSwitch(CoordinatorEntity, SwitchEntity, StuderEntity):
    """
    Representation of a Studer Switch Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.SWITCH)
        
        # The unique identifier for this sensor within Home Assistant
        self.entity_id = ENTITY_ID_FORMAT.format(entity.object_id)

        # update creation-time only attributes
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        self._attr_entity_category = self.get_entity_category()
        self._attr_device_class = None

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
            case FORMAT.BOOL:
                attr_val = value
                
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                attr_val = self._entity.options.values.get(value, value)

            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a select entity")

        if attr_val in SWITCH_VALUES_ON:
            attr_is_on = True
            attr_state = STATE_ON
            
        elif attr_val in SWITCH_VALUES_OFF:
            attr_is_on = False
            attr_state = STATE_OFF
        else:
            attr_is_on = None
            attr_state = None

        # update value if it has changed
        changed = False

        if force or (self._xcom_flash_state != self._entity.value):
            self._xcom_flash_state = self._entity.value
            self._xcom_ram_state = self._entity.valueModified

        if force or (self._attr_is_on != attr_is_on):
            self._attr_is_on = attr_is_on
            self._attr_state = attr_state
            
            self._attr_unit_of_measurement = self.get_unit()
            self._attr_icon = self.get_icon()
            changed = True
            
        return changed
    
    
    async def async_turn_on(self, **kwargs) -> None:
        """Turn the entity on."""

        match self._entity.format:
            case FORMAT.BOOL:
                data_val = 1
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                data_val = next((k for k,v in self._entity.options.items() if k in SWITCH_VALUES_ON or v in SWITCH_VALUES_ON), None)
            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a select entity")
                data_val = None
                
        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to ON ({data_val})")
            
            success = await self._coordinator.async_modify_data(self._entity, data_val)
            if success:
                self._attr_is_on = True
                self._attr_state = STATE_ON
                self._xcom_ram_state = data_val
                self.async_write_ha_state()
    
    
    async def async_turn_off(self, **kwargs) -> None:
        """Turn the entity off."""

        match self._entity.format:
            case FORMAT.BOOL:
                data_val = 0
            case FORMAT.SHORT_ENUM | FORMAT.LONG_ENUM:
                data_val = next((k for k,v in self._entity.options.items() if k in SWITCH_VALUES_OFF or v in SWITCH_VALUES_OFF), None)
            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a select entity")
                data_val = None

        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to OFF ({data_val})")
            
            success = await self._coordinator.async_modify_data(self._entity, data_val)
            if success:
                self._attr_is_on = False
                self._attr_state = STATE_OFF
                self._xcom_ram_state = data_val
                self.async_write_ha_state()
    
