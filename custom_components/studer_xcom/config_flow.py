"""config_flow.py: Config flow for DAB Pumps integration."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries, exceptions

from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.selector import selector

from homeassistant.const import (
    CONF_PORT,
    CONF_DEVICES,
)

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_USER_LEVEL,
    CONF_POLLING_INTERVAL,
    DEFAULT_USER_LEVEL,
    DEFAULT_POLLING_INTERVAL,
)
from .coordinator import (
    StuderCoordinatorFactory,
    StuderDeviceConfig,
)
from .xcom_const import (
    LEVEL,
    OBJ_TYPE,
)
from .xcom_datapoints import (
    XcomDatasetFactory,
    XcomDataset,
    XcomDatapointUnknownException,
)
from .xcom_families import (
    XcomDeviceFamilies,
    XcomDeviceFamily,
)

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register("studer_xcom")
class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize config flow."""
        self._port: int = DEFAULT_PORT
        self._user_level: str = DEFAULT_USER_LEVEL
        self._devices: list[StuderDeviceConfig] = []
        self._numbers: list[str] = []
        self._errors: dict[str,str] = {}

        self._in_reconfigure = False
        self._reconfig_entry = None

        self._coordinator = None
        self._dataset = None
        self._progress_tasks: list[asyncio.Task[None] | None] = []



    async def async_step_user(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Handle a flow initialized by the user.
        """        
        return await self.async_step_client()
    
    
    async def async_step_reconfigure(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Handle a flow to reconfigure
        """ 

        self._in_reconfigure = True

        # Load existing values
        self._reconfig_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        self._port = self._reconfig_entry.data.get(CONF_PORT, DEFAULT_PORT)
        self._user_level = self._reconfig_entry.data.get(CONF_USER_LEVEL, DEFAULT_USER_LEVEL)
        devices_data = self._reconfig_entry.data.get(CONF_DEVICES, [])

        self._devices = [StuderDeviceConfig.from_dict(device) for device in devices_data]
        
        # Show the config flow
        return await self.async_step_client()
    
    
    async def async_step_client(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 1: to get the client configuration
        """        
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step client - handle input {user_input}")
            self._port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Check if port is not already in user for another Hub
            self._errors = {}

            _LOGGER.debug(f"Check config entries for port")
            for config_entry in self.hass.config_entries.async_entries(DOMAIN):
                entry_id = config_entry.entry_id
                entry_port = config_entry.data.get(CONF_PORT, DEFAULT_PORT)

                if self._port == entry_port and self.context.get("entry_id",None) != entry_id:
                    self._errors[CONF_PORT] = f"Port is already in use by another Hub"

            if not self._errors:
                _LOGGER.debug(f"Step client - next step discover")
                return await self.async_step_progress()

        # Show the form to configure the port
        _LOGGER.debug(f"Step client - show form")
        
        return self.async_show_form(
            step_id = "client", 
            data_schema = vol.Schema({
                vol.Required(CONF_PORT, description={"suggested_value": self._port}): cv.port,
            }),
            errors = self._errors
        )


    async def async_step_progress(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 2: discover reachable Xcom devices
        """
        if self._errors:
            _LOGGER.debug(f"Step xcom_discover - revert to port input form")
            self._progress_tasks = []

            return self.async_show_progress_done(next_step_id = "client")

        progress_steps = [ # (percent, action, function)
            (0,   "xcom_connect",    self._async_xcom_connect),
            (50,  "xcom_devices",    self._async_xcom_devices),
            (100, "xcom_disconnect", self._async_xcom_disconnect),
        ]
        if not self._progress_tasks:
            self._progress_tasks = [None for _ in progress_steps]
            
        progress_task: asyncio.Task[None] | None = None
        progress_action: str = ''
        progress_percent: int = 0

        for idx, (step_percent, step_action, step_func) in enumerate(progress_steps):
            if not progress_task:
                if not self._progress_tasks[idx]:
                    _LOGGER.debug(f"Step progress - create task {step_action}")
                    self._progress_tasks[idx] = self.hass.async_create_task(step_func())

                if not self._progress_tasks[idx].done():
                    _LOGGER.debug(f"Step progress - task {step_action} not done yet")
                    progress_task = self._progress_tasks[idx]
                    progress_action = step_action
                    progress_percent = step_percent
            
        if progress_task:
            _LOGGER.debug(f"Step progress - show progress, action:{progress_action}, percent:{progress_percent}")
            return self.async_show_progress(
                step_id = "progress",
                progress_task = progress_task,
                progress_action = progress_action,
                description_placeholders = { "percent": f"{progress_percent}%" },
            )
        
        # all discovery tasks done
        _LOGGER.debug(f"Step progress - done")
        _LOGGER.debug(f"devices: {', '.join([device.code for device in self._devices])}")
        self._progress_tasks = []

        return self.async_show_progress_done(next_step_id = "numbers")


    async def _async_xcom_connect(self):
        """Test the port by connecting to the Studer Xcom client"""

        try:
            _LOGGER.info("Discover Xcom connection")
            self._coordinator = StuderCoordinatorFactory.create_temp(self._port)

            await self._coordinator.start()
            if not await self._coordinator.wait_until_connected(30):
                self._errors[CONF_PORT] = f"Xcom client did not connect to the specified port"
                return

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of connection: {e}")
            self._errors[CONF_PORT] = f"Unknown error: {e}"
        
            await self._async_xcom_disconnect(is_task=False)

        finally:
            # Ensure we go back to the flow
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )

    
    async def _async_xcom_devices(self):
        """Discover devices reachable via the Studer Xcom client"""

        try:
            _LOGGER.info("Discover Xcom devices")
            if not self._dataset:
                self._dataset = XcomDatasetFactory.create()

            # Send a couple of dummy requests, just to give the client enough time to start listening
            await asyncio.sleep(1)
            param = self._dataset.getByNr(XcomDeviceFamilies.XTENDER.nrDiscover, XcomDeviceFamilies.XTENDER.idForNr)
            addr = XcomDeviceFamilies.XTENDER.addrDevicesStart
            await self._coordinator.async_request_test(param, addr)

            await asyncio.sleep(1)     
            param = self._dataset.getByNr(XcomDeviceFamilies.RCC.nrDiscover, XcomDeviceFamilies.RCC.idForNr)
            addr = XcomDeviceFamilies.RCC.addrDevicesStart
            await self._coordinator.async_request_test(param, addr)
            await asyncio.sleep(1)     
            
            families = XcomDeviceFamilies.getList()
            family_percent = 100.0 / (len(families)+1)

            for family in families:
                # Get value for the first info nr in the family, or otherwise the first param nr
                nr = family.nrDiscover or family.nrInfosStart or family.nrParamsStart or None
                if not nr:
                    continue

                param = self._dataset.getByNr(nr, family.idForNr)

                # Iterate all addresses in the family, up to the first address that is not found
                for device_addr in range(family.addrDevicesStart, family.addrDevicesEnd+1):

                    success = await self._coordinator.async_request_test(param, device_addr)
                    if success:
                        device_code = family.get_code(device_addr)
                        _LOGGER.info(f"Found device {device_code} via {nr}:{device_addr}")

                        self._devices.append(StuderDeviceConfig(
                            address = device_addr,
                            code = device_code,
                            family = family.id,
                            numbers = family.nrDefaults
                        ))
                    else:
                        # Do not test further device addresses in this family
                        break

            if not self._devices:
                self._errors[CONF_PORT] = f"No Studer devices found via Xcom client"
                return
                
        except Exception as e:
            _LOGGER.warning(f"Exception during discover of connection: {e}")
            self._errors[CONF_PORT] = f"Unknown error: {e}"
        
            await self._async_xcom_disconnect(is_task=False)

        finally:
            # Ensure we go back to the flow
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )


    async def _async_xcom_disconnect(self, is_task=True):
        """Disconnect from the Studer Xcom client"""

        try:
            _LOGGER.info("Disconnect from Xcom client")
            if self._coordinator:
                await self._coordinator.stop()
                self._coordinator = None
        except:
            pass

        finally:
            if is_task:
                # Ensure we go back to the flow
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
                )


    async def async_step_numbers(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3: specify params and infos numbers for each device
        """
        if not self._dataset:
            self._dataset = XcomDatasetFactory.create()

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step numbers - handle input {user_input}")
            self._user_level = user_input.get(CONF_USER_LEVEL, DEFAULT_USER_LEVEL)

            # Additional validation here if needed
            self._errors = {}
            for device in self._devices:
                try:
                    val_csv = user_input[device.code] if device.code in user_input else ''
                    device.numbers = list(filter(None, [v.strip() for v in val_csv.split(',')]))

                    validate = await self._valid_numbers(device.code, device.family)
                    device.numbers = validate(device.numbers)

                except Exception as e:
                    _LOGGER.debug(f"Step numbers - validation error {e}")
                    self._errors[device.code] = str(e)

            if not self._errors:
                _LOGGER.debug(f"Step numbers - next step finish")
                self._dataset = None
                return await self.async_step_finish()

        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step numbers - build schema")
        schema = vol.Schema({
            vol.Required(CONF_USER_LEVEL, description={"suggested_value": self._user_level}): selector({
                "select": { 
                    "options": [ str(level) for level in LEVEL if level <= LEVEL.EXPERT ],
                    "mode": "dropdown"
                }
            })
        })
        for device in self._devices:
            val_csv = ','.join([str(nr) for nr in device.numbers])
        
            schema = schema.extend({
                vol.Optional(device.code, description={"suggested_value": val_csv}): cv.string
            })

        _LOGGER.debug(f"Step numbers - show form")
        return self.async_show_form(
            step_id = "numbers", 
            data_schema = schema,
            errors = self._errors
        )


    async def _valid_numbers(self, code: str, family:str) -> Callable[[Any], list[int]]:

        device_family = XcomDeviceFamilies.getById(family)
        user_level = LEVEL.from_str(self._user_level)
        
        def validate(value: Any) -> list[int]:
            if not isinstance(value, list):
                raise vol.Invalid("Expected a list")
            
            result: list[int] = []

            # Check all numbers in the list
            for val in value:
                if not val or not val.isnumeric():
                    raise vol.Invalid(f"Expected comma separated numbers, got '{val}'")
                
                # Check that the number is a valid param or infos number within this family
                nr = int(val)
                try:
                    param = self._dataset.getByNr(nr, device_family.idForNr)

                except XcomDatapointUnknownException:
                    raise vol.Invalid(f"Number {nr} is unknown for {device_family.model} devices")

                if param.obj_type not in [OBJ_TYPE.INFO, OBJ_TYPE.PARAMETER]:
                    raise vol.Invalid(f"Number {nr} is not a valid info or param")
                
                if param.level > user_level:
                    raise vol.Invalid(f"Number {nr} is not allowed with user level {user_level}")

                result.append(nr)

            return result
        
        return validate


    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Configuration and discovery has succeeded
        """
        if user_input is not None:
            # Create the integration entry
            title = f"Studer via Xcom port {self._port}"
            data = {
                CONF_PORT: self._port,
                CONF_USER_LEVEL: self._user_level,
                CONF_DEVICES: [device.as_dict() for device in self._devices],
            }
            options = {
                CONF_POLLING_INTERVAL: DEFAULT_POLLING_INTERVAL,
            }

            _LOGGER.debug(f"Step finish - (re)create entry, data:{data}, options:{options}")
            if self._in_reconfigure:
                reason = "Reconfigure finished"
                return self.async_update_reload_and_abort(self._reconfig_entry, title=title, data=data, options=options, reason=reason)
            else:
                return self.async_create_entry(title=title, data=data, options=options)
        
        # Show the form to show we are ready
        _LOGGER.debug(f"Step finish - show form")
        
        return self.async_show_form(
            step_id = "finish",
            errors = self._errors,
            last_step = True,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):

    """Handles options flow for the component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        if not self.config_entry.options:
            self.config_entry.options = {}

        self._polling_interval = None
        self._errors = None


    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            _LOGGER.debug(f"Options flow handle user input")
            self._errors = {}

            self._polling_interval = user_input.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)

            # Do we have everything we need?
            if not self._errors:
                # Value of data will be set on the options property of the config_entry instance.
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    options = {
                        CONF_POLLING_INTERVAL: self._polling_interval,
                    } 
                )
                return self.async_create_entry(title=None, data=None)

            _LOGGER.error(f"Error: {self._errors}")
        
        else:
            self._polling_interval = self.config_entry.options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)

        # Show the form with the options
        _LOGGER.debug(f"Options flow show user input form")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_POLLING_INTERVAL, default=self._polling_interval): 
                    vol.All(vol.Coerce(int), vol.Range(min=5)),
            }),
            errors = self._errors
        )
 
