"""config_flow.py: Config and Options flow for DAB Pumps integration."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from enum import Enum, StrEnum
import logging
import re
from typing import Any, Callable

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries, data_entry_flow, exceptions

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.config_entries import ConfigFlow
from homeassistant.config_entries import ConfigEntryBaseFlow
from homeassistant.config_entries import OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.selector import selector

from homeassistant.const import (
    CONF_PORT,
    CONF_DEVICES,
)

from .const import (
    CONF_PRODUCT,
    CONF_VOLTAGE,
    CONF_XCOM_VOLTAGE_AC,
    CONF_XCOM_VOLTAGE_DC,
    CONF_XCOM_PORT,
    CONF_XCOM_WEBCONFIG_URL,
    CONF_NEXT_GW_HOST,
    CONF_NEXT_GW_PORT,
    CONF_NEXT_WEBCONFIG_URL,
    CONF_USER_LEVEL,
    CONF_POLLING_INTERVAL,
    CONF_WEBCONFIG_URL,
    CONF_GATEWAY_INFO,
    CONF_CLIENT_INFO,
    DEFAULT_PRODUCT,
    DEFAULT_PRODUCT_FAMILY_NUMBERS,
    DEFAULT_XCOM_VOLTAGE_AC,
    DEFAULT_XCOM_VOLTAGE_DC,
    DEFAULT_XCOM_PORT,
    DEFAULT_NEXT_GW_HOST,
    DEFAULT_NEXT_GW_PORT,
    DEFAULT_USER_LEVEL,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    PRODUCTS,
    PRODUCTS_NUMBERS_URL,
    PRODUCTS_README_URL,
    INTEGRATION_README_URL,
    NEXT_README_URL,
    NEXT_TITLE_FMT,
    XCOM_README_URL,
    XCOM_TITLE_FMT,
)
from .coordinator import (
    StuderCoordinator,
    StuderCoordinatorFactory,
    StuderGatewayConfig,
    StuderDeviceConfig,
)
from pystuderxcom import (
    AsyncStuderDiscover,
    StuderDataset,
    StuderDatapoint,
    StuderDatapointUnknownException,
    StuderDataType,
    StuderDeviceFamilies,
    StuderDeviceFamily,
    StuderUserLevel,
)
from pystuderxcom import (
    AsyncXcomDiscover,
    XcomVoltage,
    XcomDataset,
    XcomDeviceFamilies,
)
from pystudernext import (
    AsyncNextDiscover,
    NextDataset,
    NextDeviceFamilies,
)


_LOGGER = logging.getLogger(__name__)

# Internal consts only used within config_flow
CONF_DEVICE = "device"
CONF_NUMBERS = "numbers"
CONF_NUMBERS_ACTION = "numbers_action"
CONF_NUMBERS_MENU = "numbers_menu"

class CONFIG_MODE(Enum):
    INITIAL = 0
    RECONFIG = 1
    CONFIG = 2

class PROGRESS_PHASE(Enum):
    DISCOVER_WEBCONFIG = 0
    DISCOVER_DEVICES = 1

class NUMBERS_ACTION(StrEnum):
    ADD_MENU = "add_via_menu"
    ADD_NR = "add_via_nr"
    DEL_NR = "del_via_nr"
    OPT_ADVANCED = "opt_advanced"
    DONE = "done"


def translation_key(val):
    if type(val) is not str:
        val = str(val)
    return val.lower().replace(' ','_') if val else ""


@config_entries.HANDLERS.register("studer_xcom")

class StuderFlowHandler(ConfigEntryBaseFlow):
    """
    Handle all config flows.
    """
 
    async def async_step_start(self, config_mode: CONFIG_MODE):
        """
        Start of all config flows: initial, reconfig and config/options
        """
        self._init(config_mode)

        match config_mode:
            case CONFIG_MODE.INITIAL | CONFIG_MODE.RECONFIG:
                # Steps that will be followed:
                #   1. Product       - select between Xtender / Next product range
                #   2. Progress      - discover Moxa/Next WebConfig
                #   3a. Xcom Client  - select voltage and Moxa Port
                #   3b. Next Gateway - select gateway address and port
                #   4. Progress      - discover Xcom/Next devices
                #   5. Finish        - create HA devices and entities (for default infos and params)

                _LOGGER.debug(f"Step start - next step: product")
                return await self.async_step_product()

            case CONFIG_MODE.CONFIG:
                # Steps that will be followed:
                #    1. Progress - (re-)discover Xcom/Next devices
                #    2. Numbers  - show found devices and their infos and params numbers
                #    3. Perform action:
                #       o Add_Menu      - Add info or param via menu (returns to step 2)
                #       o Add_Numbers   - Add infos or params via number (returns to step 2)
                #       o Del_Numbers   - Del infos or params via number (returns to step 2)
                #       o Opt_Advanced  - Advanced options (returns to step 2)
                #       o Done          - Done (continues to step 4)
                #    4. Finish   - (re-)create HA devices and entities (for modified infos and params)

                _LOGGER.debug(f"Step start - next step: discover Xcom")
                return await self.async_step_progress_devices()
            

    def _init(self, config_mode: CONFIG_MODE):
        """
        Initialize internal varianles
        """
        self._config_mode = config_mode

        # Get config and options if already available
        match config_mode:
            case CONFIG_MODE.INITIAL:
                config_entry = None
            case CONFIG_MODE.RECONFIG:
                config_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                self.reconfig_entry = config_entry
            case CONFIG_MODE.CONFIG:
                config_entry = self.config_entry    # self.hass.config_entries.async_get_entry(self.handler)

        _LOGGER.debug(f"existing config_entry: {config_entry}")

        configs = config_entry.data or {} if config_entry else {}
        options = config_entry.options or {} if config_entry else {}

        # Load existing values for config and options or assign defaults
        # Note that some values have moved from config to options and we fallback for backwards compatibility
        self._product = configs.get(CONF_PRODUCT, DEFAULT_PRODUCT)

        self._xcom_voltage_ac = configs.get(CONF_XCOM_VOLTAGE_AC, None) or configs.get(CONF_VOLTAGE, DEFAULT_XCOM_VOLTAGE_AC)
        self._xcom_voltage_dc = configs.get(CONF_XCOM_VOLTAGE_DC, DEFAULT_XCOM_VOLTAGE_DC)
        self._xcom_port = configs.get(CONF_XCOM_PORT, None) or configs.get(CONF_PORT, DEFAULT_XCOM_PORT)
        self._xcom_webconfig_url = configs.get(CONF_XCOM_WEBCONFIG_URL, None) or configs.get(CONF_WEBCONFIG_URL, "")

        self._next_gw_host = configs.get(CONF_NEXT_GW_HOST, DEFAULT_NEXT_GW_HOST)
        self._next_gw_port = configs.get(CONF_NEXT_GW_PORT, DEFAULT_NEXT_GW_PORT)
        self._next_webconfig_url = configs.get(CONF_NEXT_WEBCONFIG_URL, "")

        client_info = configs.get(CONF_GATEWAY_INFO, None) or configs.get(CONF_CLIENT_INFO, {})
        self._gateway_info = StuderGatewayConfig.from_dict(client_info)

        devices_data = options.get(CONF_DEVICES, None) or configs.get(CONF_DEVICES, [])
        self._devices = []
        self._devices_old = [StuderDeviceConfig.from_dict(device) for device in devices_data]

        level_str = options.get(CONF_USER_LEVEL, None) or configs.get(CONF_USER_LEVEL, str(DEFAULT_USER_LEVEL))
        self._user_level = next( (level for level in StuderUserLevel if level_str.upper()==str(level)), DEFAULT_USER_LEVEL)

        self._polling_interval = options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)      

        # Set other internal helper variables
        self._errors: dict[str,str] = {}
        self._coordinator: StuderCoordinator = None
        self._dataset: StuderDataset = None
        self._families: StuderDeviceFamilies = None
        self._discover: AsyncStuderDiscover = None

        # Progress step
        self._progress_phase = PROGRESS_PHASE.DISCOVER_WEBCONFIG
        self._progress_steps: list[tuple] = None
        self._progress_tasks: list[asyncio.Task[None] | None] = None
        self._progress_trace: list[bool] = None
        self._progress_next_step_id = None
        self._progress_err_step_id = None

        # Add param or info via menu step
        self._menu_device = None
        self._menu_family = None
        self._menu_level = DEFAULT_USER_LEVEL
        self._menu_parent_name = "Root"
        self._menu_parent_nr = ""
        self._menu_history = list()

        # Add/del param or info via menu step or via number step
        self._device_code = ""

    
    async def async_step_product(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        To let the user select the product family: Xtender or Next
        """        
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step product - handle input {user_input}")
            product = user_input.get(CONF_PRODUCT, DEFAULT_PRODUCT)
            self._product = next((p for p in PRODUCTS if translation_key(p) == product), DEFAULT_PRODUCT)

            # Validity checks - None
            self._errors = {}

            if not self._errors:
                _LOGGER.debug(f"Step product - next step: progress_webconfig")
                return await self.async_step_progress_webconfig()

        # Show the form to configure the port
        _LOGGER.debug(f"Step product - show form")
        
        return self.async_show_form(
            step_id = "product", 
            data_schema = vol.Schema({
                vol.Required(CONF_PRODUCT, description={"suggested_value": translation_key(self._product)}): selector({
                    "select": { 
                        "options": [translation_key(p) for p in PRODUCTS],
                        "mode": "dropdown",
                        "translation_key": CONF_PRODUCT
                    }
                }),
            }),
            errors = self._errors,
            last_step = False,
        )


    async def async_step_progress_webconfig(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Discover Moxa/Next Gateway WebConfig
        """
        self._progress_phase = PROGRESS_PHASE.DISCOVER_WEBCONFIG
        self._progress_steps = [ 
            # (percent, action, function)
            (0,   "webconfig",  self._async_gw_webconfig),
        ]
        self._progress_tasks = [None for idx in range(len(self._progress_steps))]
        self._progress_trace = [True for idx in range(len(self._progress_steps))]

        match self._product:
            case PRODUCTS.XCOM:
                self._progress_next_step_id = "xcom_gateway"
                self._progress_err_step_id = "xcom_gateway"
            case PRODUCTS.NEXT:
                self._progress_next_step_id = "next_gateway"
                self._progress_err_step_id = "next_gateway"
            case _:
                _LOGGER.warning(f"Step progress_webconfig - incorrect value for product: {self._product}")

        return await self.async_step_progress(user_input)


    async def async_step_xcom_gateway(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 1: to get the xcom client configuration
        """        
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step xcom_gateway - handle input {user_input}")
            voltage_ac_key = user_input.get(CONF_XCOM_VOLTAGE_AC, DEFAULT_XCOM_VOLTAGE_AC)
            voltage_dc_key = user_input.get(CONF_XCOM_VOLTAGE_DC, DEFAULT_XCOM_VOLTAGE_DC)
            self._xcom_voltage_ac = next((v for v in XcomVoltage if translation_key(v) == voltage_ac_key), DEFAULT_XCOM_VOLTAGE_AC)
            self._xcom_voltage_dc = next((v for v in XcomVoltage if translation_key(v) == voltage_dc_key), DEFAULT_XCOM_VOLTAGE_DC)
            self._xcom_port = user_input.get(CONF_XCOM_PORT, DEFAULT_XCOM_PORT)

            # Check if port is not already in user for another Hub
            self._errors = {}

            _LOGGER.debug(f"Check config entries for port")
            for config_entry in self.hass.config_entries.async_entries(DOMAIN):
                entry_id = config_entry.entry_id
                entry_port = config_entry.data.get(CONF_XCOM_PORT, DEFAULT_XCOM_PORT)

                if self._xcom_port == entry_port and self.context.get("entry_id",None) != entry_id:
                    self._errors[CONF_XCOM_PORT] = f"Port is already in use by another Hub"

            if not self._errors:
                _LOGGER.debug(f"Step xcom_gateway - next step: discover xcom_devices")
                return await self.async_step_progress_devices()

        # Show the form to configure the port
        _LOGGER.debug(f"Step xcom_gateway - show form")

        return self.async_show_form(
            step_id = "xcom_gateway", 
            data_schema = vol.Schema({
                vol.Required(CONF_XCOM_VOLTAGE_AC, description={"suggested_value": translation_key(self._xcom_voltage_ac)}): selector({
                    "select": { 
                        "options": [translation_key(v) for v in XcomVoltage if 'ac' in str(v)],
                        "mode": "dropdown",
                        "translation_key": CONF_XCOM_VOLTAGE_AC
                    }
                }),
                vol.Required(CONF_XCOM_VOLTAGE_DC, description={"suggested_value": translation_key(self._xcom_voltage_dc)}): selector({
                    "select": { 
                        "options": [translation_key(v) for v in XcomVoltage if 'dc' in str(v)],
                        "mode": "dropdown",
                        "translation_key": CONF_XCOM_VOLTAGE_DC
                    }
                }),
                vol.Required(CONF_XCOM_PORT, description={"suggested_value": self._xcom_port}): cv.port
            }),
            description_placeholders = {
                "xcom_config_url": f"[Xcom Moxa Web Config]({self._xcom_webconfig_url})" if self._xcom_webconfig_url else "Xcom Moxa Web Config",
                "xcom_readme_url": f"[Xcom-LAN config.md]({XCOM_README_URL})",
                "readme_url": INTEGRATION_README_URL
            },
            errors = self._errors,
            last_step = False,
        )


    async def async_step_next_gateway(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 1: to get the NextGateway client configuration
        """        
        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step next_gateway - handle input {user_input}")
            self._next_gw_host = user_input.get(CONF_NEXT_GW_HOST, DEFAULT_NEXT_GW_HOST)
            self._next_gw_port = user_input.get(CONF_NEXT_GW_PORT, DEFAULT_NEXT_GW_PORT)

            # Check if port is not already in user for another Hub
            self._errors = {}

            _LOGGER.debug(f"Check config entries for host+port")
            for config_entry in self.hass.config_entries.async_entries(DOMAIN):
                entry_id = config_entry.entry_id
                entry_host = config_entry.data.get(CONF_NEXT_GW_HOST, DEFAULT_NEXT_GW_HOST)
                entry_port = config_entry.data.get(CONF_NEXT_GW_PORT, DEFAULT_NEXT_GW_PORT)

                if self._next_gw_host == entry_host and self._next_gw_port == entry_port and self.context.get("entry_id",None) != entry_id:
                    self._errors[CONF_NEXT_GW_PORT] = f"Host and Port are already handled by another Hub"

            if not self._errors:
                _LOGGER.debug(f"Step next_gateway - next step: discover next_devices")
                return await self.async_step_progress_devices()

        # Show the form to configure the port
        _LOGGER.debug(f"Step next_gateway - show form")
        
        return self.async_show_form(
            step_id = "next_gateway", 
            data_schema = vol.Schema({
                vol.Required(CONF_NEXT_GW_HOST, description={"suggested_value": self._next_gw_host}): cv.host,
                vol.Required(CONF_NEXT_GW_PORT, description={"suggested_value": self._next_gw_port}): cv.port
            }),
            description_placeholders = {
                "next_config_url": f"[NextGateway Web Config]({self._next_webconfig_url})" if self._next_webconfig_url else "NextGateway Web Config",
                "next_readme_url": f"[NextGateway config.md]({NEXT_README_URL})",
                "readme_url": INTEGRATION_README_URL
            },
            errors = self._errors,
            last_step = False,
        )


    async def async_step_progress_devices(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Discover reachable Xcom devices
        """        
        self._progress_phase = PROGRESS_PHASE.DISCOVER_DEVICES
        self._progress_steps = [ 
            # (percent, action, function)
            (0,   "connect",    self._async_gw_connect),
            (30,  "details",    self._async_gw_details),
            (50,  "devices",    self._async_gw_devices),
            (100, "disconnect", self._async_gw_disconnect),
        ]
        self._progress_tasks = [None for idx in range(len(self._progress_steps))]
        self._progress_trace = [True for idx in range(len(self._progress_steps))]

        match self._config_mode:
            case CONFIG_MODE.INITIAL | CONFIG_MODE.RECONFIG:
                self._progress_next_step_id = "finish"
                self._progress_err_step_id = "xcom_client" if self._product in [PRODUCTS.XCOM] else "next_client"
                
            case CONFIG_MODE.CONFIG:
                self._progress_next_step_id = "numbers"
                self._progress_err_step_id = "numbers"

        return await self.async_step_progress(user_input)


    async def async_step_progress(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Discover Moxa WebConfig
        or
        Discover reachable Xcom devices
        """
        if self._errors:
            _LOGGER.debug(f"Step progress - done with error, phase={self._progress_phase.name}")
            self._progress_steps = None
            self._progress_tasks = None
            self._progress_trace = None
            return self.async_show_progress_done(next_step_id = self._progress_err_step_id)

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
            with suppress(UnknownFlow):
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
        return self.async_show_progress_done(next_step_id = self._progress_next_step_id)


    async def _async_gw_webconfig(self, is_task=True):
        """Try to (re-)discover the url for the Moxa/Next Gateway Web Config so we can give a better error hint"""
        try:
            match self._product:
                case PRODUCTS.XCOM:
                    _LOGGER.info(f"Discover Moxa Web Config")
                    self._xcom_webconfig_url = await AsyncXcomDiscover.discover_gateway_webconfig(self._xcom_webconfig_url)
                    if self._xcom_webconfig_url:
                        _LOGGER.info(f"Discovered Xcom/Moxa Web Config at {self._xcom_webconfig_url}")
                    else:
                        _LOGGER.info(f"Could not determine Moxa Web Config url")

                case PRODUCTS.NEXT:
                    _LOGGER.info(f"Discover NextGateway Web Config")
                    self._next_webconfig_url = await AsyncNextDiscover.discover_gateway_webconfig(self._next_webconfig_url)
                    if self._next_webconfig_url:
                        _LOGGER.info(f"Discovered NextGateway Web Config at {self._next_webconfig_url}")

                        # If no host was set yet then derive probable host ip from the webconfig url
                        if not self._next_gw_host:
                            self._next_gw_host = self._next_webconfig_url.replace("http://", "")
                    else:
                        _LOGGER.info(f"Could not determine NextGateway Web Config url")

                case _:
                    _LOGGER.warning(f"Step progress gateway webconfig - incorrect value for product: {self._product}")

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of Gateway Web Config: {e}")
            self._errors[CONF_WEBCONFIG_URL] = f"Unknown error: {e}"
        
        finally:
            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            if is_task:
                self.hass.async_create_task( self._async_configure(flow_id=self.flow_id) )


    async def _async_gw_vars_init(self):
        """Initialize all temporary values used during discovery and choosing numbers"""

        # Reset everything as product, voltage, host or port may have changed
        await self._async_gw_vars_clear()

        match self._product:
            case PRODUCTS.XCOM:
                self._coordinator = await StuderCoordinatorFactory.async_create_temp(
                    product=self._product, 
                    xcom_voltage_ac=self._xcom_voltage_ac, 
                    xcom_voltage_dc=self._xcom_voltage_dc, 
                    xcom_port=self._xcom_port, 
                )
                self._dataset = await XcomDataset.async_get_instance(self._xcom_voltage_ac, self._xcom_voltage_dc)
                self._discover = AsyncXcomDiscover(self._coordinator._api, self._dataset)
                self._families = await XcomDeviceFamilies.async_get_instance()

            case PRODUCTS.XCOM:
                self._coordinator = await StuderCoordinatorFactory.async_create_temp(
                    product=self._product, 
                    next_gw_host=self._next_gw_host, 
                    next_gw_port=self._next_gw_port,
                )
                self._dataset = await NextDataset.async_get_instance()
                self._discover = AsyncNextDiscover(self._coordinator._api, self._dataset)
                self._families = await NextDeviceFamilies.async_get_instance()

            case _:
                _LOGGER.warning(f"Step progress-gateway-connect - incorrect value for product: {self._product}")


    async def _async_gw_vars_clear(self):
        """Clear all temporary values used during discovery and choosing numbers"""

        if self._coordinator and self._coordinator.is_temp:
            _LOGGER.info("Disconnect from gateway")
            await self._coordinator.stop()

        self._coordinator = None
        self._dataset = None
        self._discover = None
        self._families = None
        
        XcomDataset.del_instance()
        NextDataset.del_instance()
        
    
    async def _async_gw_connect(self, is_task=True):
        """Test the port by connecting to the Studer Xcom client / NextGateway"""

        try:
            _LOGGER.info("Discover gateway connection")

            # Make sure our _coordinator, _dataset and _families variables are set for the correct product
            await self._async_gw_vars_init()

            # Let the coordinator connect to the gateway
            if await self._coordinator.start():
                _LOGGER.info("Gateway connected")
            else:
                _LOGGER.info(f"Could not connect to Studer gateway.")
                self._errors[CONF_XCOM_PORT] = f"Xcom gateway did not connect; make sure the Home Assistant IP address and this port are configured via the local Xcom Moxy Web Config"
                self._errors[CONF_NEXT_GW_HOST] = f"Could not connect to NextGateway; make sure the specified gateway host and port match the setting in the NextGateway Web Config"                        

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of gateway connection: {e}")
            self._errors[CONF_XCOM_PORT] = f"Unknown error: {e}"
            self._errors[CONF_NEXT_GW_HOST] = f"Unknown error: {e}"

        finally:
            # Cleanup
            if CONF_XCOM_PORT in self._errors or CONF_NEXT_GW_HOST in self._errors:
                await self._async_gw_disconnect(is_task=False)

            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            if is_task:
                self.hass.async_create_task( self._async_configure(flow_id=self.flow_id) )

    
    async def _async_gw_details(self, is_task=True):
        """Discover information about the Studer Xcom client / NextGateway"""

        try:
            _LOGGER.info("Discover gateway details")
            
            if not self._discover or not self._coordinator or self._coordinator.product != self._product:
                raise Exception("process _async_gw_connect was not called prior to _async_gw_devices")

            # Discover information about the Xcom client
            info = await self._discover.discover_gateway_info()
            if info:
                _LOGGER.info(f"Gateway details detected; host={info.host}, guid={info.guid}")
                self._gateway_info = StuderGatewayConfig(
                    info.host,
                    info.guid,
                )
            else:
                _LOGGER.info(f"Gateway details not detected.")
                match self._product:
                    case PRODUCTS.XCOM: self._errors[CONF_XCOM_PORT] = f"No information found for Studer Xcom Gateway"
                    case PRODUCTS.NEXT:    self._errors[CONF_NEXT_GW_HOST] = f"No information found for Studer Next Gateway"
                return

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of gateway details: {e}")
            self._errors[CONF_XCOM_PORT] = f"Unknown error: {e}"
            self._errors[CONF_NEXT_GW_HOST] = f"Unknown error: {e}"

        finally:
            # Cleanup
            if CONF_XCOM_PORT in self._errors or CONF_NEXT_GW_HOST in self._errors:
                await self._async_gw_disconnect(is_task=False)

            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            if is_task:
                self.hass.async_create_task( self._async_configure(flow_id=self.flow_id) )


    async def _async_gw_devices(self, is_task=True):
        """Discover devices reachable via the Studer Xcom client / Next Gateway"""

        try:
            _LOGGER.info("Discover Xcom devices")
            
            if not self._discover or not self._coordinator or self._coordinator.product != self._product:
                raise Exception("process _async_gw_connect was not called prior to _async_gw_devices")

            # Discover Studer Xcom/Next devices
            discovered_devices = await self._discover.discover_devices(getExtendedInfo = True)
            if not discovered_devices:
                self._errors[CONF_XCOM_PORT] = f"No Studer devices found via Xcom Gateway"
                self._errors[CONF_NEXT_GW_HOST] = f"No Studer devices found via Next Gateway"
                return

            default_family_numbers = DEFAULT_PRODUCT_FAMILY_NUMBERS.get(self._product, {})

            self._devices_new = []
            for dd in discovered_devices:

                device_new = StuderDeviceConfig(
                    product = self._product,
                    code = dd.code,
                    address = dd.address,
                    slave = dd.slave,
                    family_id = dd.family_id,
                    family_model = dd.family_model,
                    device_model = dd.device_model,
                    serial = dd.serial,
                    hw_version = dd.hw_version,
                    sw_version = dd.sw_version,
                    om_version = dd.om_version,
                    numbers = default_family_numbers.get(dd.family_id, [])  
                )

                # In reconfigure, did we already have a deviceConfig for this device?
                # If so, then keep the previously configured numbers
                device_old = next((d for d in self._devices_old if StuderDeviceConfig.match(d, device_new)), None)
                if device_old:
                    device_new.numbers = device_old.numbers

                self._devices.append(device_new)

        except Exception as e:
            _LOGGER.warning(f"Exception during discover of connection: {e}")
            self._errors[CONF_XCOM_PORT] = f"Unknown error: {e}"
            self._errors[CONF_NEXT_GW_HOST] = f"Unknown error: {e}"

        finally:
            # Cleanup
            if CONF_XCOM_PORT in self._errors or CONF_NEXT_GW_HOST in self._errors:
                await self._async_gw_disconnect(is_task=False)

            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            if is_task:
                self.hass.async_create_task( self._async_configure(flow_id=self.flow_id) )


    async def _async_gw_disconnect(self, is_task=True):
        """Disconnect from the Studer Xcom/Next Gateway"""

        try:
            if self._coordinator and self._coordinator.is_temp:
                _LOGGER.info("Disconnect from gateway")
                await self._coordinator.stop()

            # do not unload self._dataset or self._familis, etc. They are used later on during 'numbers', 'add_menu' and 'add_number' steps
        except:
            pass

        finally:
            # Sleep because async_create_task cannot handle an immediate return
            await asyncio.sleep(1)  

            # Ensure we go back to the flow
            if is_task:
                self.hass.async_create_task( self._async_configure(flow_id=self.flow_id) )


    async def _async_configure(self, flow_id):
        """
        Give control back to the flow
        """

        # When called from OptionsFlow, 'hass.config_entries.flow.async_configure' will throw a UnknowFlow exception.
        # Everything else seems to work as expected, so we just suppress this exception.
        # When called from ConfigFlow it does not have this behavior and does not throw the exception.
        with suppress(UnknownFlow):
            await self.hass.config_entries.flow.async_configure(flow_id=flow_id)


    async def async_step_numbers(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3: specify params and infos numbers for each device
        """

        # Make sure our _dataset and _families variables are set for the correct product
        await self._async_gw_vars_init()

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step numbers - handle input {user_input}")
            action = user_input.get(CONF_NUMBERS_ACTION, "")

            # Additional validation here if needed
            self._errors = {}
            if not self._errors:
                match action:
                    case NUMBERS_ACTION.DONE:
                        _LOGGER.debug(f"Step numbers - next step: finish")
                        self._dataset = None
                        self._families = None
                        return await self.async_step_finish()
                    
                    case NUMBERS_ACTION.ADD_MENU:
                        _LOGGER.debug(f"Step numbers - next step: add_menu")
                        return await self.async_step_add_menu()

                    case NUMBERS_ACTION.ADD_NR:
                        _LOGGER.debug(f"Step numbers - next step: add_numbers")
                        return await self.async_step_add_numbers()

                    case NUMBERS_ACTION.DEL_NR:
                        _LOGGER.debug(f"Step numbers - next step: del_numbers")
                        return await self.async_step_del_numbers()

                    case NUMBERS_ACTION.OPT_ADVANCED:
                        _LOGGER.debug(f"Step numbers - next step: options_advanced")
                        return await self.async_step_opt_advanced()

                    case _:
                        _LOGGER.warning(f"Step numbers - unknown action: {action}")
                        pass # continue below to show form again

        # Build a Markdown string containing all found devices and datapoints
        _LOGGER.debug(f"Step numbers - build markdown")
        datapoints_md =  "| level | number | description |\n"
        datapoints_md += "| :---- | :----- | :---------- |\n"

        for idx,device in enumerate(self._devices):
            family: StuderDeviceFamily = self._families.get_by_id(device.family_id)
            datapoints_md += f"| &nbsp; | &nbsp; | &nbsp; |\n" if idx > 0 else ""
            datapoints_md += f"| &nbsp; | *{device.code}* | {family.model} |\n"
            
            for nr in device.numbers:
                datapoint: StuderDatapoint = self._dataset.get_by_nr(nr, family)
                datapoints_md += f"| {datapoint.userlevel_r} | {nr} | {datapoint.name} |\n"

        # Build the schema for the form and show the form
        _LOGGER.debug(f"Step numbers - build schema")
        schema = vol.Schema({
            vol.Required(CONF_NUMBERS_ACTION, description={"suggested_value": ""}): selector({
                "select": { 
                    "options": [
                        NUMBERS_ACTION.ADD_MENU, 
                        NUMBERS_ACTION.ADD_NR, 
                        NUMBERS_ACTION.DEL_NR, 
                        NUMBERS_ACTION.OPT_ADVANCED, 
                        NUMBERS_ACTION.DONE,
                    ],
                    "mode": "dropdown",
                    "translation_key": CONF_NUMBERS_ACTION
                }
            })

        })

        _LOGGER.debug(f"Step numbers - show form")
        return self.async_show_form(
            step_id="numbers",
            data_schema = schema,
            description_placeholders = {
                "numbers_url": PRODUCTS_NUMBERS_URL.get(self._product),
                "datapoints": datapoints_md,
            },
            errors = self._errors,
            last_step = False,
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
            level = next( (level for level in StuderUserLevel if translation_key(level) == level_key), DEFAULT_USER_LEVEL)

            # Additional validation here if needed
            self._device_code = device.code if device is not None else ""
            self._user_level = level
            self._errors = {}
            if not self._errors:
                if device is not None:
                    _LOGGER.debug(f"Step add_menu - next step: add_menu_items")
                    self._menu_device = device
                    self._menu_family = self._families.get_by_id(device.family_id)
                    self._menu_level = level
                    self._menu_parent_name = "Root"
                    self._menu_parent_nr = ""
                    self._menu_history = list()
                    return await self.async_step_add_menu_items()
                else:
                    _LOGGER.debug(f"Step add_menu - next step: numbers")
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
                    "options": [ translation_key(level) for level in StuderUserLevel if StuderUserLevel.INFO <= level <= StuderUserLevel.EXPERT ],
                    "mode": "dropdown",
                    "translation_key": CONF_USER_LEVEL
                }
            })
        })

        _LOGGER.debug(f"Step add_menu - show form")
        return self.async_show_form(
            step_id="add_menu",
            data_schema = schema,
            errors = self._errors,
            last_step = False,
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
                    _LOGGER.debug(f"Step add_menu - next step: numbers (back)")
                    return await self.async_step_numbers()
                
                case "parent":
                    (self._menu_parent_name, self._menu_parent_nr) = self._menu_history.pop()
                    # continue below to show parent menu

                case _:
                    datapoint = self._dataset.get_by_nr(int(key))
                    if datapoint.data_type == StuderDataType.MENU:
                        self._menu_history.append( (self._menu_parent_name, self._menu_parent_nr) )
                        self._menu_parent_name = datapoint.name
                        self._menu_parent_nr = str(datapoint.nr)
                        # continue below to show sub menu
                    else:
                        dev_numbers = set(self._menu_device.numbers or [])
                        dev_numbers.add(datapoint.nr)
                        self._menu_device.numbers = sorted(dev_numbers)
                        _LOGGER.debug(f"menu_device new: {self._menu_device}")
                        _LOGGER.debug(f"all device: {self._devices}")

                        _LOGGER.debug(f"Step add_menu - added {datapoint.nr} to {self._menu_device.code}")
                        _LOGGER.debug(f"Step add_menu - next step: numbers")
                        return await self.async_step_numbers()                      
                    
        # Build the menu options for the form and show the form
        _LOGGER.debug(f"Step add_menu_items - build menu for {self._menu_parent_nr} {self._menu_family.id}")
        self._menu_options = {}
        self._menu_options["back"] = "back" #"Back to numbers overview"

        if len(self._menu_history) > 0:
            self._menu_options["parent"] = "parent" #"Back to parent menu"

        items: list[StuderDatapoint] = self._dataset.get_menu_items(self._menu_family, self._menu_parent_nr)
        for item in items:
            if item.userlevel_r <= self._menu_level:
                nr = f"{item.userlevel_r} {item.nr} - " if item.nr >= 1000 else ""
                name = item.name
                menu = " ►" if item.data_type == StuderDataType.MENU else ""
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
            step_id="add_menu_items",
            data_schema = schema,
            description_placeholders = {
                "menu_name": self._menu_parent_name
            },
            errors = self._errors,
            last_step = False,
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

                    _LOGGER.debug(f"Step add_numbers - added {str.join(',', [str(n) for n in add_numbers])} to {device.code}")

                except Exception as e:
                    _LOGGER.debug(f"Step add_numbers - validation error {e}")
                    self._errors[CONF_NUMBERS] = str(e)

            if not self._errors:
                _LOGGER.debug(f"Step add_numbers - next step: numbers")
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
            step_id="add_numbers",
            data_schema = schema,
            description_placeholders = {
                "numbers_url": PRODUCTS_NUMBERS_URL.get(self._product, ""),
            },
            errors = self._errors,
            last_step = False,
        )


    async def async_step_del_numbers(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Step 3c: Remove params or infos numbers for a device by directly entering the numbers
        """
        numbers_csv = ""

        if user_input is not None:
            # Get form data
            _LOGGER.debug(f"Step del_numbers - handle input {user_input}")
            device_key = user_input.get(CONF_DEVICE, "")
            device = next( (device for device in self._devices if translation_key(device.code) == device_key), None)

            numbers_csv = user_input.get(CONF_NUMBERS, "")
            numbers = list(filter(None, [v.strip() for v in numbers_csv.split(',')]))

            # Additional validation here if needed
            self._device_code = device.code if device is not None else None
            self._errors = {}
            if device is not None and len(numbers) > 0:
                try:
                    validate = await self._valid_numbers(device.code, device.family_id)
                    del_numbers = validate(numbers, check_family=False, check_level=False)

                    device.numbers = [n for n in device.numbers if n not in del_numbers]

                    _LOGGER.debug(f"Step del_numbers - deleted {str.join(',', [str(n) for n in del_numbers])} from {device.code}")

                except Exception as e:
                    _LOGGER.debug(f"Step del_numbers - validation error {e}")
                    self._errors[CONF_NUMBERS] = str(e)

            if not self._errors:
                _LOGGER.debug(f"Step del_numbers - next step: numbers")
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
            step_id="del_numbers",
            data_schema = schema,
            description_placeholders = {
                "numbers_url": PRODUCTS_NUMBERS_URL.get(self._product, ""),
            },
            errors = self._errors,
            last_step = False,
        )


    async def _valid_numbers(self, code: str, family_id:str) -> Callable[[Any], list[int]]:

        family = self._families.get_by_id(family_id)
        
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
                        param = self._dataset.get_by_nr(nr, family)
                    except StuderDatapointUnknownException:
                        raise vol.Invalid(f"Number {nr} is unknown for {family.model} devices")

                    if param.data_type in [StuderDataType.MENU, StuderDataType.ERROR, StuderDataType.INVALID]:
                        raise vol.Invalid(f"Number {nr} is not a valid info or param")
                
                if check_level:
                    if param.userlevel_r > self._user_level:
                        raise vol.Invalid(f"Number {nr} is not allowed with user level {self._user_level}")

                result.append(nr)

            return result
        
        return validate


    async def async_step_opt_advanced(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Manage advanced options.
        """
        if user_input is not None:
            _LOGGER.debug(f"Step options_advanced - handle input {user_input}")
            self._errors = {}
            self._polling_interval = user_input.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)

            # Do we have everything we need?
            if not self._errors:
                _LOGGER.debug(f"Step options_advanced - next step: numbers")
                return await self.async_step_numbers()

            _LOGGER.error(f"Error: {self._errors}")

        # Show the form with the options
        _LOGGER.debug(f"Step options_advanced - show form")

        return self.async_show_form(
            step_id="opt_advanced",
            data_schema=vol.Schema({
                vol.Required(CONF_POLLING_INTERVAL, default=self._polling_interval): 
                    vol.All(vol.Coerce(int), vol.Range(min=5)),
            }),
            errors = self._errors,
            last_step = False,
        )
 

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Configuration and discovery has succeeded
        """

        # Clear our temporary _coordinator, _dataset and _families
        await self._async_gw_vars_clear()
        
        # Create the integration entry
        

        data = {
            CONF_PRODUCT: self._product,
            CONF_GATEWAY_INFO: self._gateway_info.as_dict(),
        }
        match self._product:
            case PRODUCTS.XCOM:
                data[CONF_XCOM_VOLTAGE_AC] = self._xcom_voltage_ac
                data[CONF_XCOM_VOLTAGE_DC] = self._xcom_voltage_dc
                data[CONF_XCOM_PORT] = self._xcom_port
                data[CONF_XCOM_WEBCONFIG_URL] = self._xcom_webconfig_url

                title = str.format(XCOM_TITLE_FMT, port=self._xcom_port)
                unique_id = self._gateway_info.guid or f"{self._gateway_info.host}:{self._xcom_port}"

            case PRODUCTS.NEXT:
                data[CONF_NEXT_GW_HOST] = self._next_gw_host
                data[CONF_NEXT_GW_PORT] = self._next_gw_port
                data[CONF_NEXT_WEBCONFIG_URL] = self._next_webconfig_url
                
                title = str.format(NEXT_TITLE_FMT, host=self._next_gw_host)
                unique_id = self._gateway_info.guid or f"{self._gateway_info.host}:{self._next_gw_port}"

            case _:
                raise ValueError(f"Unexpected value for parameter 'product': '{self._product}'")
            
        options = {
            CONF_USER_LEVEL: str(self._user_level),
            CONF_DEVICES: [device.as_dict() for device in self._devices],
            CONF_POLLING_INTERVAL: self._polling_interval,
        }

        _LOGGER.debug(f"Step finish - (re)create entry, data:{data}, options:{options}")
        match self._config_mode:
            case CONFIG_MODE.INITIAL:
                # Use client_info.guid as unique_id for this config flow to avoid the same hub being setup twice
                # Fallback to alternatives if needed
                _LOGGER.debug(f"set_unique_id: {unique_id}")

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
    
                return self.async_create_entry(title=title, data=data, options=options)
            
            case CONFIG_MODE.RECONFIG:
                reason = "Reconfigure finished"
                return self.async_update_reload_and_abort(entry=self.reconfig_entry, title=title, data=data, options=options, reason=reason)
            
            case CONFIG_MODE.CONFIG:
               self.hass.config_entries.async_update_entry(entry=self.config_entry, title=title, data=data, options = options)
               return self.async_create_entry(title=None, data=None)
            
            

class ConfigFlowHandler(ConfigFlow, StuderFlowHandler, domain=DOMAIN):
    """
    Handle config and reconfig flows.
    """
    
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """
        Get the options flow for this handler.
        Points to ourself as this class handles both config and options flow.
        """
        return OptionsFlowHandler()
    

    async def async_step_user(self, user_input: dict[str,Any] | None = None) -> FlowResult:
        """
        Handle an initial config flow (started by adding new integration).
        """ 
        _LOGGER.debug(f"Step user (ConfigFlow) - start config flow")
        return await self.async_step_start(CONFIG_MODE.INITIAL)


    # Reconfigure is no longer supported.
    # Most of the old functionality is moved from 'reconfigure' to 'configure' (OptionsFlow).
    # The only remaining use for it would be to change the listening port, but that would 
    # change all unique_id's of devices and entities. So hase the same effect as removing
    # the config_entry and then creating a new one.
    #
    # async def async_step_reconfigure(self, user_input: dict[str,Any] | None = None) -> FlowResult:
    #     """
    #     Handle a reconfigure flow (started by pressing 'reconfigure' in existing integration)
    #     """ 
    #     _LOGGER.debug(f"Step reconfigure (ConfigFlow) - start config flow")
    #     return await self.async_step_start(CONFIG_MODE.RECONFIG)
    

class OptionsFlowHandler(OptionsFlow, StuderFlowHandler):
    """
    Handle options flows.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Handle an options flow (started by pressing 'configure' in existing integration)
        """         
        _LOGGER.debug(f"Step init (OptionsFlow) - start config flow")
        return await self.async_step_start(CONFIG_MODE.CONFIG)



