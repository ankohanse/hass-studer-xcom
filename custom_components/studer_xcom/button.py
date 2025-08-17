import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.components.button import ENTITY_ID_FORMAT
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



_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of select entities
    """
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
    await helper.async_setup_entry(Platform.BUTTON, StuderButton, async_add_entities)


class StuderButton(CoordinatorEntity, ButtonEntity, StuderEntity):
    """
    Representation of a Studer Button Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.BUTTON)
        
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
        self._update_value(force=True)
    
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        
        # Update value
        if self._update_value():
            self.async_write_ha_state()
    
    
    def _update_value(self, force:bool=False):
        """Process any changes in value"""
       
        changed = False

        # Nothing to update
        return changed
    

    async def async_press(self) -> None:
        """Press the button."""

        data_val = 1
        _LOGGER.info(f"Set {self.entity_id} to Signal ({data_val})")
            
        success = await self._coordinator.async_modify_data(self._entity, data_val)
        if success:
            self._update_value(force=True)
            self.async_write_ha_state()
