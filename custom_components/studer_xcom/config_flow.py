"""config_flow.py: Config flow for DAB Pumps integration."""
from __future__ import annotations

import asyncio
from enum import Enum, StrEnum
import logging
import re
from typing import Any, Callable

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries, exceptions

from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.data_entry_flow import section
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
    CONF_VOLTAGE,
    CONF_USER_LEVEL,
    CONF_POLLING_INTERVAL,
    CONF_WEBCONFIG_URL,
    DEFAULT_VOLTAGE,
    DEFAULT_USER_LEVEL,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_FAMILY_NUMBERS,
    INTEGRATION_README_URL,
    MOXA_README_URL,
    XCOM_APPENDIX_URL,
)
from .coordinator import (
    StuderCoordinatorFactory,
    StuderDeviceConfig,
)
from aioxcom import (
    LEVEL,
    OBJ_TYPE,
    FORMAT,
    VOLTAGE,
    XcomDiscover,
    XcomDataset,
    XcomDatapoint,
    XcomDatapointUnknownException,
    XcomDeviceFamilies,
    XcomDeviceFamily,
)

_LOGGER = logging.getLogger(__name__)

# Internal consts only used within config_flow
CONF_DEVICE = "device"
CONF_NUMBERS = "numbers"
CONF_NUMBERS_ACTION = "numbers_action"
CONF_NUMBERS_MENU = "numbers_menu"

class NUMBERS_ACTION(StrEnum):
    ADD_MENU = "add_via_menu"
    ADD_NR = "add_via_nr"
    DEL_NR = "del_via_nr"
    DONE = "done"

class PROGRESS_PHASE(Enum):
    MOXA_DISCOVER = 0
    XCOM_DISCOVER = 2


def translation_key(val):
    if type(val) is not str:
        val = str(val)
    return val.lower().replace(' ','_') if val else ""


@config_entries.HANDLERS.register("studer_xcom")
class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize config flow."""
        self._voltage: str = DEFAULT_VOLTAGE
        self._port: int = DEFAULT_PORT
        self._webconfig_url: str = None
        self._user_level: LEVEL = DEFAULT_USER_LEVEL
        self._devices: list[StuderDeviceConfig] = []
        self._devices_old: list[StuderDeviceConfig] = []

        self._polling_interval = DEFAULT_POLLING_INTERVAL

        self._errors: dict[str,str] = {}
        self._in_reconfigure = False
        self._reconfig_entry = None

        self._coordinator = None
        self._dataset = None

        # Progress step
        self._progress_phase = PROGRESS_PHASE.MOXA_DISCOVER
        self._progress_steps: list[tuple] = None
        self._progress_tasks: list[asyncio.Task[None] | None] = None
        self._progress_trace: list[bool] = None

        # Add param or info via menu step
        self._menu_device = None
        self._menu_family = None
        self._menu_level = DEFAULT_USER_LEVEL
        self._menu_parent_name = "Root"
        self._menu_parent_nr = 0
        self._menu_history = list()

        # Add/del param or info via menu step or via number step
        self._device_code = ""


    async def async_step_user(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Handle a flow initialized by the user.
        """ 
        _LOGGER.debug(f"Step user - start config flow")

        _LOGGER.debug(f"Step user - next step discover Moxa")
        self._progress_phase = PROGRESS_PHASE.MOXA_DISCOVER
        return await self.async_step_progress()
    
    
    async def async_step_reconfigure(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Handle a flow to reconfigure
        """ 
        _LOGGER.debug(f"Step reconfigure - start config flow")
        self._in_reconfigure = True

        # Load existing values for config
        self._reconfig_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        self._voltage = self._reconfig_entry.data.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)
        self._port = self._reconfig_entry.data.get(CONF_PORT, DEFAULT_PORT)

        level = self._reconfig_entry.data.get(CONF_USER_LEVEL, "")
        self._user_level = LEVEL.from_str(level, DEFAULT_USER_LEVEL)

        self._webconfig_url = self._reconfig_entry.data.get(CONF_WEBCONFIG_URL, "")
        devices_data = self._reconfig_entry.data.get(CONF_DEVICES, [])

        self._devices = []
        self._devices_old = [StuderDeviceConfig.from_dict(device) for device in devices_data]

        # Load existing values for options
        self._polling_interval = self._reconfig_entry.options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)      
        
        # Show the config flow
        _LOGGER.debug(f"Step reconfigure - next step discover Moxa")
        self._progress_phase = PROGRESS_PHASE.MOXA_DISCOVER
        return await self.async_step_progress()
    
    
    async def async_step_client(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 1: to get the client configuration
        """        
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step client - handle input {user_input}")
            voltage_key = user_input.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)
            self._voltage = next((v for v in VOLTAGE if translation_key(v) == voltage_key), DEFAULT_VOLTAGE)
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
                _LOGGER.debug(f"Step client - next step discover Xcom")
                self._progress_phase = PROGRESS_PHASE.XCOM_DISCOVER
                return await self.async_step_progress()

        # Show the form to configure the port
        _LOGGER.debug(f"Step client - show form")
        
        return self.async_show_form(
            step_id = "client", 
            data_schema = vol.Schema({
                vol.Required(CONF_VOLTAGE, description={"suggested_value": translation_key(self._voltage)}): selector({                    "select": { 
                        "options": [translation_key(v) for v in VOLTAGE],
                        "mode": "dropdown",
                        "translation_key": CONF_VOLTAGE
                    }
                }),
                vol.Required(CONF_PORT, description={"suggested_value": self._port}): cv.port
            }),
            description_placeholders = {
                "moxa_config_url": f"[Xcom Moxa Web Config]({self._webconfig_url})" if self._webconfig_url else "Xcom Moxa Web Config",
                "moxa_readme_url": f"[Xcom-LAN config.md]({MOXA_README_URL})",
                "readme_url": INTEGRATION_README_URL
            },
            errors = self._errors
        )


    async def async_step_progress(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 0: discover Moxa WebConfig (phase 1) 
        Step 2: discover reachable Xcom devices (phase 2)
        """
        if self._errors:
            match self._progress_phase:
                case PROGRESS_PHASE.MOXA_DISCOVER | PROGRESS_PHASE.XCOM_DISCOVER:
                    self._progress_steps = None
                    self._progress_tasks = None
                    self._progress_trace = None
                    return self.async_show_progress_done(next_step_id = "client")

        # On first entry for the current phase, define the steps and tasks 
        if not self._progress_steps:
            match self._progress_phase:
                case PROGRESS_PHASE.MOXA_DISCOVER:
                    self._progress_steps = [ # (percent, action, function)
                        (0,   "xcom_webconfig",  self._async_xcom_webconfig),
                    ]

                case PROGRESS_PHASE.XCOM_DISCOVER:
                    self._progress_steps = [ # (percent, action, function)
                        (0,   "xcom_connect",    self._async_xcom_connect),
                        (50,  "xcom_devices",    self._async_xcom_devices),
                        (100, "xcom_disconnect", self._async_xcom_disconnect),
                    ]

                case _:
                    raise NotImplementedError(f"progress_phase: {self._progress_phase.name}")

            self._progress_tasks = [None for idx in range(len(self._progress_steps))]
            self._progress_trace = [True for idx in range(len(self._progress_steps))]

        # Run through all defined steps and tasks for the current phase            
        progress_task: asyncio.Task[None] | None = None
        progress_action: str = ''
        progress_percent: int = 0

        for idx, (step_percent, step_action, step_func) in enumerate(self._progress_steps):
            if not progress_task:
                if not self._progress_tasks[idx]:
                    _LOGGER.debug(f"Step progress - create task {step_action}, phase={self._progress_phase.name}, idx={idx}")
                    self._progress_tasks[idx] = self.hass.async_create_task(step_func())

                if not self._progress_tasks[idx].done():
                    _LOGGER.debug(f"Step progress - task {step_action} not done yet")
                    progress_task = self._progress_tasks[idx]
                    progress_action = step_action
                    progress_percent = step_percent
                elif self._progress_trace[idx]:
                    _LOGGER.debug(f"Step progress - task {step_action} done")
                    self._progress_trace[idx] = False
            
        if progress_task:
            _LOGGER.debug(f"Step progress - show progress, action:{progress_action}, percent:{progress_percent}")
            return self.async_show_progress(
                step_id = "progress",
                progress_task = progress_task,
                progress_action = progress_action,
                description_placeholders = { "percent": f"{progress_percent}%" },
            )
        
        # all tasks done for the current phase
        _LOGGER.debug(f"Step progress - done, phase={self._progress_phase.name}")
        self._progress_steps = None
        self._progress_tasks = None
        self._progress_trace = None

        match self._progress_phase:
            case PROGRESS_PHASE.MOXA_DISCOVER:
                return self.async_show_progress_done(next_step_id = "client")
            
            case PROGRESS_PHASE.XCOM_DISCOVER:
                _LOGGER.debug(f"found devices: {', '.join([device.code for device in self._devices])}")

                return self.async_show_progress_done(next_step_id = "numbers")
            
            case _:
                raise NotImplementedError(f"progress_phase: {self._progress_phase}")


    async def _async_xcom_connect(self):
        """Test the port by connecting to the Studer Xcom client"""

        try:
            _LOGGER.info("Discover Xcom connection")
            if not self._coordinator:
                self._coordinator = StuderCoordinatorFactory.create_temp(self._voltage, self._port)

            if await self._coordinator.start():
                _LOGGER.info("Xcom client connected")
            else:
                _LOGGER.info(f"Xcom client did not connect.")
                self._errors[CONF_PORT] = f"Xcom client did not connect; make sure the Home Assistant IP address and this port are configured via the local Xcom Moxy Web Config"

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of connection: {e}")
            self._errors[CONF_PORT] = f"Unknown error: {e}"

        finally:
            # Cleanup
            if CONF_PORT in self._errors:
                await self._async_xcom_disconnect(is_task=False)

            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )

    
    async def _async_xcom_webconfig(self):
        """Try to (re-)discover the url for the Xcom Web Config so we can give a better error hint"""

        try:
            _LOGGER.info(f"Discover Xcom Moxa Web Config")
            self._webconfig_url = await XcomDiscover.discoverMoxaWebConfig(self._webconfig_url)

            if self._webconfig_url:
                _LOGGER.info(f"Discovered Xcom Moxa Web Config at {self._webconfig_url}")
            else:
                _LOGGER.info(f"Could not determine Xcom Moxa Web Config url")

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of Xcom Moxa Web Config: {e}")
            self._errors[CONF_WEBCONFIG_URL] = f"Unknown error: {e}"
        
        finally:
            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )

    
    async def _async_xcom_devices(self):
        """Discover devices reachable via the Studer Xcom client"""

        try:
            _LOGGER.info("Discover Xcom devices")
            
            if not self._dataset:
                self._dataset = await XcomDataset.create(self._voltage)

            helper = XcomDiscover(self._coordinator._api, self._dataset)
            devices = await helper.discoverDevices(getExtendedInfo = True)
            if not devices:
                self._errors[CONF_PORT] = f"No Studer devices found via Xcom client"
                return
            
            self._devices = []
            for device in devices:
                # In reconfigure, did we already have a deviceConfig for this device?
                device_old = next((d for d in self._devices_old if StuderDeviceConfig.match(d, device)), None)

                self._devices.append(StuderDeviceConfig(
                    code = device.code,
                    addr = device.addr,
                    family_id = device.family_id,
                    family_model = device.family_model,
                    device_model = device.device_model,
                    hw_version = device.hw_version,
                    sw_version = device.sw_version,
                    fid = device.fid,
                    numbers = device_old.numbers if device_old else DEFAULT_FAMILY_NUMBERS.get(device.family_id, [])  
                ))
                
        except Exception as e:
            _LOGGER.warning(f"Exception during discover of connection: {e}")
            self._errors[CONF_PORT] = f"Unknown error: {e}"

        finally:
            # Cleanup
            if CONF_PORT in self._errors:
                await self._async_xcom_disconnect(is_task=False)

            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_configure(flow_id=self.flow_id)
            )


    async def _async_xcom_disconnect(self, is_task=True):
        """Disconnect from the Studer Xcom client"""

        try:
            if self._coordinator and self._coordinator.is_temp:
                _LOGGER.info("Disconnect from Xcom client")
                await self._coordinator.stop()

            self._coordinator = None
        except:
            pass

        finally:
            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

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
            self._dataset = await XcomDataset.create(self._voltage)

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step numbers - handle input {user_input}")
            action = user_input.get(CONF_NUMBERS_ACTION, "")

            # Additional validation here if needed
            self._errors = {}
            if not self._errors:
                match action:
                    case NUMBERS_ACTION.DONE:
                        _LOGGER.debug(f"Step numbers - next step finish")
                        self._dataset = None
                        return await self.async_step_finish()
                    
                    case NUMBERS_ACTION.ADD_MENU:
                        _LOGGER.debug(f"Step numbers - next step add_menu")
                        return await self.async_step_add_menu()

                    case NUMBERS_ACTION.ADD_NR:
                        _LOGGER.debug(f"Step numbers - next step add_numbers")
                        return await self.async_step_add_numbers()

                    case NUMBERS_ACTION.DEL_NR:
                        _LOGGER.debug(f"Step numbers - next step del_numbers")
                        return await self.async_step_del_numbers()

                    case _:
                        _LOGGER.warning(f"Step numbers - unknown action: {action}")
                        pass # continue below to show form again

        # Build a Markdown string containing all found devices and datapoints
        _LOGGER.debug(f"Step numbers - build markdown")
        datapoints_md =  "| level | number | description |\n"
        datapoints_md += "| :---- | :----- | :---------- |\n"

        for idx,device in enumerate(self._devices):
            family: XcomDeviceFamily = XcomDeviceFamilies.getById(device.family_id)
            datapoints_md += f"| &nbsp; | &nbsp; | &nbsp; |\n" if idx > 0 else ""
            datapoints_md += f"| &nbsp; | *{device.code}* | {family.model} |\n"
            
            for nr in device.numbers:
                datapoint: XcomDatapoint = self._dataset.getByNr(nr, family.idForNr)
                datapoints_md += f"| {datapoint.level} | {nr} | {datapoint.name} |\n"

        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step numbers - build schema")
        schema = vol.Schema({
            vol.Required(CONF_NUMBERS_ACTION, description={"suggested_value": ""}): selector({
                "select": { 
                    "options": [NUMBERS_ACTION.ADD_MENU, NUMBERS_ACTION.ADD_NR, NUMBERS_ACTION.DEL_NR, NUMBERS_ACTION.DONE],
                    "mode": "dropdown",
                    "translation_key": CONF_NUMBERS_ACTION
                }
            })

        })

        _LOGGER.debug(f"Step numbers - show form")
        return self.async_show_form(
            step_id = "numbers", 
            data_schema = schema,
            description_placeholders = {
                "numbers_url": XCOM_APPENDIX_URL,
                "datapoints": datapoints_md,
            },
            errors = self._errors
        )


    async def async_step_add_menu(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3a: add params or infos numbers for a device via a menu
        """
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step add_menu - handle input {user_input}")
            device_key = user_input.get(CONF_DEVICE, "")
            device = next( (device for device in self._devices if translation_key(device.code) == device_key), None)

            level_key = user_input.get(CONF_USER_LEVEL, "")
            level = next( (level for level in LEVEL if translation_key(level) == level_key), DEFAULT_USER_LEVEL)

            # Additional validation here if needed
            self._device_code = device.code if device is not None else ""
            self._user_level = level
            self._errors = {}
            if not self._errors:
                if device is not None:
                    _LOGGER.debug(f"Step add_menu - next step add_menu_items")
                    self._menu_device = device
                    self._menu_family = XcomDeviceFamilies.getById(device.family_id)
                    self._menu_level = level
                    self._menu_parent_name = "Root"
                    self._menu_parent_nr = 0
                    self._menu_history = list()
                    return await self.async_step_add_menu_items()
                else:
                    _LOGGER.debug(f"Step add_menu - next step numbers")
                    return await self.async_step_numbers()
                    
        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step add_menu - build schema")
        schema = vol.Schema({
            vol.Optional(CONF_DEVICE, description={"suggested_value": translation_key(self._device_code)}): selector({
                "select": { 
                    "options": [translation_key(device.code) for device in self._devices],
                    "mode": "dropdown",
                    "translation_key": CONF_DEVICE
                }
            }),
            vol.Required(CONF_USER_LEVEL, description={"suggested_value": translation_key(self._user_level)}): selector({
                "select": { 
                    "options": [ translation_key(level) for level in LEVEL if level <= LEVEL.EXPERT ],
                    "mode": "dropdown",
                    "translation_key": CONF_USER_LEVEL
                }
            })
        })

        _LOGGER.debug(f"Step add_menu - show form")
        return self.async_show_form(
            step_id = "add_menu", 
            data_schema = schema,
            errors = self._errors
        )


    async def async_step_add_menu_items(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3a: add params or infos numbers for a device via a menu
        """
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step add_menu_items - handle input {user_input}")
            chosen = user_input.get(CONF_NUMBERS_MENU, None)
            key = next( (k for k,v in self._menu_options.items() if v == chosen), None)
            _LOGGER.debug(f"Step add_menu_items - handle input key:{key}")

            match key:
                case "back":
                    _LOGGER.debug(f"Step add_menu - next step numbers (back)")
                    return await self.async_step_numbers()
                
                case "parent":
                    (self._menu_parent_name, self._menu_parent_nr) = self._menu_history.pop()
                    # continue below to show parent menu

                case _:
                    datapoint = self._dataset.getByNr(int(key))
                    if datapoint.format == FORMAT.MENU:
                        self._menu_history.append( (self._menu_parent_name, self._menu_parent_nr) )
                        self._menu_parent_name = datapoint.name
                        self._menu_parent_nr = datapoint.nr
                        # continue below to show sub menu
                    else:
                        dev_numbers = set(self._menu_device.numbers or [])
                        dev_numbers.add(datapoint.nr)
                        self._menu_device.numbers = sorted(dev_numbers)
                        _LOGGER.debug(f"menu_device new: {self._menu_device}")
                        _LOGGER.debug(f"all device: {self._devices}")

                        _LOGGER.debug(f"Step add_menu - next step numbers (added {datapoint.nr} to {self._menu_device.code})")
                        return await self.async_step_numbers()                      
                    
        # Build the menu options for the form and show the form
        _LOGGER.debug(f"Step add_menu_items - build menu for {self._menu_parent_nr} {self._menu_family.idForNr}")
        self._menu_options = {}
        self._menu_options["back"] = "back" #"Back to numbers overview"

        if len(self._menu_history) > 0:
            self._menu_options["parent"] = "parent" #"Back to parent menu"

        items = self._dataset.getMenuItems(self._menu_parent_nr, self._menu_family.idForNr)
        for item in items:
            if item.level <= self._menu_level:
                nr = f"{item.level} {item.nr} - " if item.nr >= 1000 else ""
                name = item.name
                menu = " ►" if item.format == FORMAT.MENU else ""
                self._menu_options[str(item.nr)] = f"{nr}{name}{menu}"

        _LOGGER.debug(f"Step add_menu_items - build schema")
        schema = vol.Schema({
            vol.Required(CONF_NUMBERS_MENU): selector({
                "select": { 
                    "options": list(self._menu_options.values()),
                    "mode": "list",
                    "translation_key": CONF_NUMBERS_MENU
                }
            })
        })

        _LOGGER.debug(f"Step add_menu_items - show form")
        return self.async_show_form(
            step_id = "add_menu_items", 
            data_schema = schema,
            description_placeholders = {
                "menu_name": self._menu_parent_name
            },
            errors = self._errors
        )


    async def async_step_add_numbers(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3b: add params or infos numbers for a device by directly entering the numbers
        """
        numbers_csv = ""

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step add_numbers - handle input {user_input}")
            device_key = user_input.get(CONF_DEVICE, "")
            device = next( (device for device in self._devices if translation_key(device.code) == device_key), None)

            numbers_csv = user_input.get(CONF_NUMBERS, "")
            numbers = list(filter(None, [v.strip() for v in numbers_csv.split(',')]))

            _LOGGER.debug(f"Step add_numbers - debug; numbers_csv={numbers_csv}, numbers={numbers}, device={device}")

            # Additional validation here if needed
            self._device_code = device.code if device is not None else None
            self._errors = {}
            if device is not None and len(numbers) > 0:
                try:
                    validate = await self._valid_numbers(device.code, device.family_id)
                    add_numbers = validate(numbers, check_family=True, check_level=False)

                    dev_numbers = set(device.numbers or [])
                    dev_numbers.update(add_numbers)
                    device.numbers = sorted(dev_numbers)

                except Exception as e:
                    _LOGGER.debug(f"Step add_numbers - validation error {e}")
                    self._errors[CONF_NUMBERS] = str(e)

            if not self._errors:
                _LOGGER.debug(f"Step add_numbers - next step view_numbers")
                return await self.async_step_numbers()

        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step add_numbers - build schema")
        schema = vol.Schema({
            vol.Optional(CONF_DEVICE, description={"suggested_value": translation_key(self._device_code)}): selector({
                "select": { 
                    "options": [translation_key(device.code) for device in self._devices],
                    "mode": "dropdown",
                    "translation_key": CONF_DEVICE
                }
            }),
            vol.Optional(CONF_NUMBERS, description={"suggested_value": numbers_csv}): cv.string
        })

        _LOGGER.debug(f"Step add_numbers - show form")
        return self.async_show_form(
            step_id = "add_numbers", 
            data_schema = schema,
            description_placeholders = {
                "numbers_url": XCOM_APPENDIX_URL,
            },
            errors = self._errors
        )


    async def async_step_del_numbers(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3c: Remove params or infos numbers for a device by directly entering the numbers
        """
        numbers_csv = ""

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step add_numbers - handle input {user_input}")
            device_key = user_input.get(CONF_DEVICE, "")
            numbers_csv = user_input.get(CONF_NUMBERS, "")

            device = next( (device for device in self._devices if translation_key(device.code) == device_key), None)
            numbers = list(filter(None, [v.strip() for v in numbers_csv.split(',')]))

            # Additional validation here if needed
            self._device_code = device.code if device is not None else None
            self._errors = {}
            if device is not None and len(numbers) > 0:
                try:
                    validate = await self._valid_numbers(device.code, device.family_id)
                    numbers = validate(numbers, check_family=False, check_level=False)

                    device.numbers = [n for n in device.numbers if n not in numbers]

                except Exception as e:
                    _LOGGER.debug(f"Step del_numbers - validation error {e}")
                    self._errors[CONF_NUMBERS] = str(e)

            if not self._errors:
                _LOGGER.debug(f"Step del_numbers - next step view_numbers")
                return await self.async_step_numbers()

        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step del_numbers - build schema")
        schema = vol.Schema({
            vol.Optional(CONF_DEVICE, description={"suggested_value": translation_key(self._device_code)}): selector({
                "select": { 
                    "options": [translation_key(device.code) for device in self._devices],
                    "mode": "dropdown",
                    "translation_key": CONF_DEVICE
                }
            }),
            vol.Optional(CONF_NUMBERS, description={"suggested_value": numbers_csv}): cv.string
        })

        _LOGGER.debug(f"Step del_numbers - show form")
        return self.async_show_form(
            step_id = "del_numbers", 
            data_schema = schema,
            description_placeholders = {
                "numbers_url": XCOM_APPENDIX_URL,
            },
            errors = self._errors
        )


    async def _valid_numbers(self, code: str, family_id:str) -> Callable[[Any], list[int]]:

        family = XcomDeviceFamilies.getById(family_id)
        
        def validate(value: Any, check_family=True, check_level=True) -> list[int]:
            if not isinstance(value, list):
                raise vol.Invalid("Expected a list")
            
            result: list[int] = []

            # Check all numbers in the list
            for val in value:
                if not val or not val.isnumeric():
                    raise vol.Invalid(f"Expected comma separated numbers, got '{val}'")
                
                # Check that the number is a valid param or infos number within this family
                nr = int(val)

                if check_family:
                    try:
                        param = self._dataset.getByNr(nr, family.idForNr)
                    except XcomDatapointUnknownException:
                        raise vol.Invalid(f"Number {nr} is unknown for {family.model} devices")

                    if param.obj_type not in [OBJ_TYPE.INFO, OBJ_TYPE.PARAMETER]:
                        raise vol.Invalid(f"Number {nr} is not a valid info or param")

                    if param.format in [FORMAT.MENU, FORMAT.ERROR, FORMAT.INVALID]:
                        raise vol.Invalid(f"Number {nr} is not a valid info or param")
                
                if check_level:
                    if param.level > self._user_level:
                        raise vol.Invalid(f"Number {nr} is not allowed with user level {self._user_level}")

                result.append(nr)

            return result
        
        return validate


    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Configuration and discovery has succeeded
        """

        # Create the integration entry
        title = f"Studer via Xcom port {self._port}"
        data = {
            CONF_VOLTAGE: self._voltage,
            CONF_PORT: self._port,
            CONF_WEBCONFIG_URL: self._webconfig_url,
            CONF_USER_LEVEL: str(self._user_level),
            CONF_DEVICES: [device.as_dict() for device in self._devices],
        }
        options = {
            CONF_POLLING_INTERVAL: self._polling_interval,
        }

        _LOGGER.debug(f"Step finish - (re)create entry, data:{data}, options:{options}")
        if self._in_reconfigure:
            reason = "Reconfigure finished"
            return self.async_update_reload_and_abort(self._reconfig_entry, title=title, data=data, options=options, reason=reason)
        else:
            return self.async_create_entry(title=title, data=data, options=options)


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
 
