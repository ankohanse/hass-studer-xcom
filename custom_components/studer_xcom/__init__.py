"""__init__.py: The Studer Xcom integration."""

from __future__ import annotations

import asyncio
import logging
import json
from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigType
from homeassistant.const import Platform
from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.translation import async_get_translations
from homeassistant.exceptions import ConfigEntryNotReady


from .coordinator import (
    StuderCoordinatorFactory,
    StuderCoordinator
)

from homeassistant.const import (
    CONF_PORT,
)

from .const import (
    DOMAIN,
    PLATFORMS,
    TITLE_FMT,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if not isinstance(entry.unique_id, str):
            hass.config_entries.async_update_entry(entry, unique_id=str(entry.unique_id))
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the Studer Xcom platforms from a config entry."""

    # Assign the HA configured log level of this module to the aioxcom module
    log_level: int = _LOGGER.getEffectiveLevel()
    lib_logger: logging.Logger = logging.getLogger("aioxcom")
    lib_logger.setLevel(log_level)

    _LOGGER.info(f"Logging at {logging.getLevelName(log_level)}")

    # Get properties from the config_entry
    port = config_entry.data[CONF_PORT]
    title = str.format(TITLE_FMT, port=port)
    
    _LOGGER.info(f"Setup config entry for {title}")

    # Get a Coordinator instance for this port and start it
    # We force to create a fresh instance, otherwise data updates don't happen if this setup_entry was triggered by a reload
    coordinator: StuderCoordinator = await StuderCoordinatorFactory.async_create(hass, config_entry, force_create=True)
    if not await coordinator.start():
        raise ConfigEntryNotReady(f"Timout while waiting for Studer Xcom client to connect to our port {port}.")
    
    # Create devices
    await coordinator.async_create_devices(config_entry)
    
    # No need to fetch initial data; 
    # we already have what we need from config_entry plus 
    # the stored data for each entity from the last HA run
    
    # Forward to all platforms (sensor, switch, ...)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Cleanup entities and devices
    await coordinator.async_cleanup_entities(config_entry)
    await coordinator.async_cleanup_devices(config_entry)

    # Reload entry when it is updated
    config_entry.async_on_unload(config_entry.add_update_listener(_async_update_listener))

    # Perform coordinator stop actions when Home Assistant shuts down or config-entry unloads
    @callback
    async def _async_coordinator_stop(*_: Any) -> None:
        _LOGGER.info(f"Stopping {title}")
        await coordinator.stop()
    
    config_entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, _async_coordinator_stop))
    config_entry.async_on_unload(_async_coordinator_stop)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unloading the Studer Xcom platforms."""

    # Get  our Coordinator instance for this port and stop it
    coordinator: StuderCoordinator = await StuderCoordinatorFactory.async_create(hass, config_entry)
    await coordinator.stop()

    success = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    return success


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Fired after update of Config Options."""

    _LOGGER.debug(f"Detect update of config options {config_entry.options}")
    await hass.config_entries.async_reload(config_entry.entry_id)