"""__init__.py: The Studer Xcom integration."""

from __future__ import annotations

import asyncio
import logging
import json
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigType
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
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
    API,
    COORDINATOR,
    HELPER,
    STARTUP_MESSAGE,
    DEFAULT_PORT,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.info(STARTUP_MESSAGE)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    _clear_hass_data(hass)

    for entry in hass.config_entries.async_entries(DOMAIN):
        if not isinstance(entry.unique_id, str):
            hass.config_entries.async_update_entry(
                entry, unique_id=str(entry.unique_id)
            )
    return True


def _clear_hass_data(hass):
    hass.data[DOMAIN] = {
        API: {},         # key is port
        COORDINATOR: {}, # key is port
        HELPER: {}       # key is port
    }


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the Studer Xcom platforms from a config entry."""

    # Get properties from the config_entry
    port = config_entry.data[CONF_PORT]
    
    _LOGGER.info(f"Setup config entry for port '{port}")

    # Get  our Coordinator instance for this port and start it
    coordinator: StuderCoordinator = StuderCoordinatorFactory.create(hass, config_entry)
    await coordinator.start()
    
    if not await coordinator.wait_until_connected():
        raise ConfigEntryNotReady(f"Timout while waiting for Studer Xcom client to connect to our port {port}.")
    
    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    await coordinator.async_config_entry_first_refresh()
    
    # Forward to all platforms (sensor, switch, ...)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Reload entry when it is updated
    # config_entry.async_on_unload(config_entry.add_update_listener(_async_update_listener))
    config_entry.add_update_listener(_async_update_listener)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unloading the Studer Xcom platforms."""

    # Get  our Coordinator instance for this port and stop it
    coordinator: StuderCoordinator = StuderCoordinatorFactory.create(hass, config_entry)
    await coordinator.stop()

    success = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if success:
        # Force re-create of Coordinator on a subsequent async_setup_entry
        _clear_hass_data(hass)

    return success


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Fired after update of Config Options."""

    _LOGGER.debug(f"Detect update of config options {config_entry.options}")
    await hass.config_entries.async_reload(config_entry.entry_id)