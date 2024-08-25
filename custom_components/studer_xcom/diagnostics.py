"""Provides diagnostics for custom component."""

import logging

from copy import deepcopy
from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from homeassistant.const import (
    CONF_PORT,
)

from .const import (
    DIAGNOSTICS_REDACT,
)

from .coordinator import (
    StuderCoordinatorFactory,
    StuderCoordinator,
)


_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    port = config_entry.data[CONF_PORT]
    _LOGGER.info(f"Retrieve diagnostics for install {port}")
    
    coordinator: StuderCoordinator = StuderCoordinatorFactory.create(hass, config_entry)
    coordinator_data = await coordinator.async_get_diagnostics()

    return {
        "config": {
            "data": async_redact_data(config_entry.data, DIAGNOSTICS_REDACT),
            "options": async_redact_data(config_entry.options, DIAGNOSTICS_REDACT),
        },
        "coordinator": async_redact_data(coordinator_data, DIAGNOSTICS_REDACT),
    }
