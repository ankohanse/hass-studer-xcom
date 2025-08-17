import logging

from homeassistant.components.select import SelectEntity
from homeassistant.components.select import ENTITY_ID_FORMAT
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
       
        if self._entity.format != FORMAT.SHORT_ENUM and self._entity.format != FORMAT.LONG_ENUM:
            _LOGGER.error(f"Unexpected format ({self._entity.format}) for a select entity")

        value = self._entity.valueModified if self._entity.valueModified is not None else self._entity.value

        attr_val = self._entity.options.get(str(value), value) if value!=None else None

        # update value if it has changed
        changed = False
        
        if force or (self._xcom_flash_state != self._entity.value):
            self._xcom_flash_state = self._entity.value
            self._xcom_ram_state = self._entity.valueModified

        if force or (self._attr_current_option != attr_val):
            self._attr_current_option = attr_val

            self._attr_unit_of_measurement = self.get_unit()
            self._attr_icon = self.get_icon()
            changed = True

        return changed
    
    
    async def async_select_option(self, option: str) -> None:
        """Change the selected option"""

        data_val = next((k for k,v in self._entity.options.items() if v == option), None)
        if data_val is not None:
            _LOGGER.info(f"Set {self.entity_id} to {option} ({data_val})")
                
            success = await self._coordinator.async_modify_data(self._entity, data_val)
            if success:
                self._attr_current_option = option
                self._xcom_ram_state = option
                self.async_write_ha_state()
    
    