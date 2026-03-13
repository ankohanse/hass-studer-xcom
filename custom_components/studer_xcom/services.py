
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall, ServiceResponse, SupportsResponse

from .coordinator import (
    StuderCoordinatorFactory,
    StuderCoordinator
)

from .const import (
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


GET_MESSAGE_SERVICE_NAME = "get_message"
GET_MESSAGE_SCHEMA = vol.Schema({
    vol.Required("index"): int
})

async def async_setup_services(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """
    Setup all services for the integration
    """

    # Setup the 'get_message' service
    async def get_message(call: ServiceCall) -> ServiceResponse:
        _LOGGER.debug(f"service 'get_message' called with call: {call}")

        # Get a Coordinator instance for this config_entry
        coordinator: StuderCoordinator = await StuderCoordinatorFactory.async_create(hass, config_entry)
        if coordinator is None:
            return None
        
        return await coordinator.async_get_message(call.data['index'])

    hass.services.async_register(
         domain = DOMAIN,
         service = GET_MESSAGE_SERVICE_NAME,
         service_func = get_message,
         schema = GET_MESSAGE_SCHEMA,
         supports_response = SupportsResponse.ONLY,
    )