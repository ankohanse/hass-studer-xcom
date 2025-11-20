import logging

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.datetime import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from datetime import datetime
from datetime import timezone

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
from pystuderxcom import (
    XcomFormat
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of number entities
    """
    helper = await StuderEntityHelperFactory.async_create(hass, config_entry)
    await helper.async_setup_entry(Platform.DATETIME, StuderDateTime, async_add_entities)


class StuderDateTime(CoordinatorEntity, DateTimeEntity, StuderEntity):
    """
    Representation of a Studer DateTime Entity.
    
    Could be a configuration setting that is part of a pump like ESybox, Esybox.mini
    Or could be part of a communication module like DConnect Box/Box2
    """
    
    def __init__(self, coordinator: StuderCoordinator, entity: StuderEntityData) -> None:
        """ Initialize the sensor. """
        CoordinatorEntity.__init__(self, coordinator)
        StuderEntity.__init__(self, coordinator, entity, Platform.DATETIME)
        
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

        # Exception from normal behavior: Datetime entity is only used to display/set the current date+time.
        # After it is set, the time in _entity.value will automatically update every minute.
        # The value as set in _entity.valueModified will no longer be relevant and must be ignored. 
        value = self._entity.value     

        match self._entity.format:
            case XcomFormat.INT32:
                # Studer entity value is seconds since 1 Jan 1970 in local timezone. DateTimeEntity expects UTC
                # When converting we assume the studer local timezone equals the HomeAssistant timezone (Settings->General).
                if value is not None:
                    ts_local = int(value)
                    dt_local = dt_util.utc_from_timestamp(ts_local).replace(tzinfo=self._coordinator.time_zone)
                    attr_val = dt_local
                else:
                    attr_val = None

            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a datetime entity")
                return
        
        # update value if it has changed
        changed = False

        if force or (self._xcom_state != self._entity.value):
            # Exception from normal behavior: Datetime entity is only used to display/set the current date+time.
            # After it is set, the time in _entity.value will automatically update every minute.
            # The value as set in _entity.valueModified will no longer be relevant and must be ignored.
            # Therefore we assign xcom_state here, not xcom_ram_state and xcom_flash state.
            self._xcom_state = self._entity.value
            changed = True
        
        if force or (self._attr_native_value != attr_val):
            self._attr_state = attr_val
            self._attr_native_value = attr_val

            self._attr_icon = self.get_icon()
            changed = True

        return changed    
    
    
    async def async_set_value(self, value: datetime) -> None:
        """Change the date/time"""
        
        match self._entity.format:
            case XcomFormat.INT32:
                # DateTimeEntity value is UTC, Studer expects seconds since 1 Jan 1970 in local timezone
                # When converting we assume the studer local timezone equals the HomeAssistant timezone (Settings->General).
                dt_local = value.astimezone(self._coordinator.time_zone)
                ts_local = dt_util.as_timestamp(dt_local.replace(tzinfo=timezone.utc))
                entity_value = int(ts_local)

            case _:
                _LOGGER.error(f"Unexpected format ({self._entity.format}) for a datetime entity")
                return
        
        _LOGGER.debug(f"Set {self.entity_id} to {value} ({entity_value})")

        # Exception from normal behavior: Datetime entity is only used to display/set the current date+time.
        # After it is set, the time in _entity.value will automatically update every minute.
        # The value as set in _entity.valueModified will no longer be relevant and must be ignored.
        success = await self._coordinator.async_modify_data(self._entity, entity_value, set_modified=False)
        if success:
            self._update_value(force=True)
            self.async_write_ha_state()


