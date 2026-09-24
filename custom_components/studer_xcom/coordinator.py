"""coordinator.py: responsible for gathering data."""

import asyncio
import collections
import logging
import re

from collections import namedtuple
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, cast

from homeassistant.components.diagnostics import REDACTED
from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.core import async_get_hass
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity_registry
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from homeassistant.const import (
    CONF_PORT, 
    CONF_DEVICES,
)

from .const import (
    CONF_CLIENT_INFO,
    CONF_GATEWAY_INFO,
    CONF_NEXT_GW_HOST,
    CONF_NEXT_GW_PORT,
    CONF_PRODUCT,
    CONF_XCOM_PORT,
    CONF_XCOM_VOLTAGE_AC,
    CONF_XCOM_VOLTAGE_DC,
    DEFAULT_NEXT_GW_HOST,
    DEFAULT_NEXT_GW_PORT,
    DEFAULT_PRODUCT,
    DEFAULT_XCOM_VOLTAGE_AC,
    DEFAULT_XCOM_VOLTAGE_DC,
    DOMAIN,
    NAME,
    MANUFACTURER,
    COORDINATOR,
    PREFIX_ID,
    PREFIX_NAME,
    PRODUCTS,
    CONF_VOLTAGE,
    CONF_XCOM_VOLTAGE_AC,
    CONF_XCOM_VOLTAGE_DC,
    CONF_POLLING_INTERVAL,
    DEFAULT_XCOM_VOLTAGE_AC,
    DEFAULT_XCOM_VOLTAGE_DC,
    DEFAULT_XCOM_PORT,
    DEFAULT_POLLING_INTERVAL,
    REQ_RETRIES,
    REQ_TIMEOUT,
    CACHE_WRITE_PERIOD,
)
from pystudernext import (  # pystudernext and pystuderxcom both contain exactly the same shared studer classes
    AsyncStuderApi,
    StuderDataset,
    StuderDatapoint,
    StuderDeviceFamilies,
    StuderDeviceFamily,
    StuderDiscoveredGateway,
    StuderValueItem,
    StuderValueSet,
)
from pystuderxcom import (
    AsyncXcomApiTcp,
    XcomApiTcpMode,
    #AJH XcomApiConnectException,
    XcomApiTimeoutException,
    XcomApiReadException,
    XcomApiWriteException,
    XcomApiResponseIsError,
    XcomApiUnpackException,
    XcomDataset,
    XcomDatapoint,
    XcomDeviceFamilies,
)
from pystudernext import (
    AsyncNextApi,
    NextApiConnectException,
    NextApiTimeoutException,
    NextApiReadException,
    NextApiUpdateException,
    NextApiUnpackException,
    NextDataset,
    NextDeviceFamilies,
)


_LOGGER = logging.getLogger(__name__)

MODIFIED_PARAMS = "ModifiedParams"
MODIFIED_PARAMS_TS = "ModifiedParamsTs"


class StuderGatewayConfig(StuderDiscoveredGateway):
    def __init__(self, host, guid):
        # From StuderDiscoveredGateway
        self.host = host
        self.guid = guid

    @staticmethod
    def from_dict(d: dict[str,Any]):
        return StuderGatewayConfig(
            d.get("host", None) or d.get("ip", None),
            d.get("guid", None),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this client info."""
        return {
            "host": self.host,
            "guid": self.guid,
        }
    
    def __str__(self) -> str:
        return f"StuderGatewayConfig(ip={self.ip}, guid={self.guid})"

    def __repr__(self) -> str:
        return self.__str__()


class StuderDeviceConfig():
    def __init__(self, product, code, address=None, slave=None, family_id=None, family_model=None, device_model=None, serial=None, hw_version=None, sw_version=None, om_version=None, numbers=[]):
        self.product = product
        self.code = code
        self.address_or_slave = address or slave    # addr is used for Xcom and slave for Next, but are essentialy the same
        self.family_id = family_id
        self.family_model = family_model
        self.device_model = device_model
        self.serial = serial
        self.hw_version = hw_version
        self.sw_version = sw_version
        self.om_version = om_version
        self.numbers = numbers

    @property
    def slave(self):
        return self.address_or_slave

    @property
    def address(self):
        return self.address_or_slave
    
    @staticmethod
    def match(a, b):
        if not isinstance(a, StuderDeviceConfig) or not isinstance(b, StuderDeviceConfig):
            return False

        if a.product != b.product:
            return False

        # Either match code or match addr/slave and family_id
        if a.code == b.code:
            return True
        if a.address_or_slave == b.address_or_slave and a.family_id == b.family_id:
            return True
                
        return False

    @staticmethod
    def from_dict(d: dict[str,Any]):
        return StuderDeviceConfig(
            product = d.get("product") or PRODUCTS.XCOM,
            code = d.get("code"),
            address = d.get("address"),
            slave = d.get("slave"),
            family_id = d.get("family_id"),
            family_model = d.get("family_model"),
            device_model = d.get("device_model"),
            serial = d.get("serial") or d.get("fid"),
            hw_version = d.get("hw_version"),
            sw_version = d.get("sw_version"),
            om_version = d.get("om_version"),
            numbers = d.get("numbers"),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this device config."""
        return {
            "product": self.product,
            "code": self.code,
            "address": self.address if self.product in [PRODUCTS.XCOM] else None,
            "slave": self.slave if self.product in [PRODUCTS.NEXT] else None,
            "family_id": self.family_id,
            "family_model": self.family_model,
            "device_model": self.device_model,
            "serial": self.serial,
            "hw_version": self.hw_version,
            "sw_version": self.sw_version,
            "om_version": self.om_version,
            "numbers": self.numbers,
        }
    
    def __str__(self) -> str:
        match self.product:
            case PRODUCTS.XCOM:
                return f"StuderDeviceConfig(product={self.product}, code={self.code}, family_id={self.family_id}, address={self.address}, numbers={self.numbers})"
            case PRODUCTS.NEXT:
                return f"StuderDeviceConfig(product={self.product}, code={self.code}, family_id={self.family_id}, slave={self.slave}, numbers={self.numbers})"

    def __repr__(self) -> str:
        return self.__str__()


class StuderEntityData():
    def __init__(self, datapoint: StuderDatapoint, object_id: str, unique_id: str, device_id: str, device_code: str, device_address: int):

        self.datapoint: StuderDatapoint = datapoint

        self.object_id: str = object_id
        self.unique_id:str = unique_id
        self.weight: float = 1
        self.value: Any = None
        self.valueModified: bool = None

        self.device_id: str = device_id
        self.device_code: str = device_code
        self.device_address: int = device_address


class StuderCoordinatorFactory:
    
    @staticmethod
    async def async_create(hass: HomeAssistant, config_entry: ConfigEntry, force_create: bool = False):
        """
        Get existing Coordinator for a config entry, or create a new one if it does not yet exist
        """
    
        # Sanity check
        if not DOMAIN in hass.data:
            hass.data[DOMAIN] = {}
        if not COORDINATOR in hass.data[DOMAIN]:
            hass.data[DOMAIN][COORDINATOR] = {}
            
        # Get properties from the config_entry
        config = config_entry.data
        options = config_entry.options

        # already created?
        coordinator = hass.data[DOMAIN][COORDINATOR].get(config_entry.entry_id, None)
        if coordinator:
            # Verify that config and options are still the same (== and != do a recursive dict compare)
            if coordinator.config != config or coordinator.options != options:
                # Not the same. Force recreate of the coordinator
                force_create = True

            if force_create:
                await coordinator.stop()
                coordinator = None

        if not coordinator:
            # Get an instance of our coordinator. This is unique to this config_entry
            _LOGGER.debug(f"Create coordinator")
            coordinator = StuderCoordinator(hass, config, options)

            hass.data[DOMAIN][COORDINATOR][config_entry.entry_id] = coordinator
            
        return coordinator


    @staticmethod
    async def async_create_temp(product, xcom_voltage_ac=None, xcom_voltage_dc=None, xcom_port=None, next_gw_host=None, next_gw_port=None):
        """
        Get temporary Coordinator for a given port.
        This coordinator will only provide limited functionality
        (connection test and device discovery)
        """
    
        # Sanity check
        hass = async_get_hass()
        if not DOMAIN in hass.data:
            hass.data[DOMAIN] = {}
        if not COORDINATOR in hass.data[DOMAIN]:
            hass.data[DOMAIN][COORDINATOR] = {}
            
        # Mimick properties from the config_entry
        config: dict[str,Any] = {
            CONF_PRODUCT: product,
            CONF_XCOM_VOLTAGE_AC: xcom_voltage_ac,
            CONF_XCOM_VOLTAGE_DC: xcom_voltage_dc,
            CONF_XCOM_PORT: xcom_port,
            CONF_NEXT_GW_HOST: next_gw_host,
            CONF_NEXT_GW_PORT: next_gw_port
        }
        options: dict[str,Any] = {
            CONF_DEVICES: [],
        }
        
        # Already have a coordinator for this port and voltage?
        coordinator = None
        for c in hass.data[DOMAIN][COORDINATOR].values():
            p = c.config.get(CONF_PRODUCT, DEFAULT_PRODUCT)
            xp  = c.config.get(CONF_XCOM_PORT, DEFAULT_XCOM_PORT)
            xac = c.config.get(CONF_XCOM_VOLTAGE_AC, None) or c.config.get(CONF_VOLTAGE, DEFAULT_XCOM_VOLTAGE_AC)
            xdc = c.config.get(CONF_XCOM_VOLTAGE_DC, DEFAULT_XCOM_VOLTAGE_DC)
            nh = c.config.get(CONF_NEXT_GW_HOST, DEFAULT_NEXT_GW_HOST)
            np = c.config.get(CONF_NEXT_GW_PORT, DEFAULT_NEXT_GW_PORT)

            if p==product:
                if p in [PRODUCTS.XCOM] and xp==xcom_port and xac==xcom_voltage_ac and xdc==xcom_voltage_dc:
                    coordinator = c
                    break
                if p in [PRODUCTS.NEXT] and nh==next_gw_host and np==next_gw_port:
                    coordinator = c
                    break            

        if not coordinator:
            # Get a temporary instance of our coordinator. This is unique to this port and voltage
            _LOGGER.debug(f"create temp coordinator, config: {config}, options: {options}")
            coordinator = StuderCoordinator(hass, config, options, is_temp=True)
        else:
            _LOGGER.debug(f"reuse existing coordinator")

        return coordinator
    

class StuderCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, config: dict[str,Any], options: dict[str,Any], is_temp=False):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name = NAME,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval = timedelta(seconds=options.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)),
            update_method = self._async_update_data,
            always_update = True,
        )

        self._config: dict[str,Any] = config
        self._options: dict[str,Any] = options
        self._is_temp = is_temp

        self._product: PRODUCTS = config.get(CONF_PRODUCT, DEFAULT_PRODUCT)
        self._xcom_voltage_ac: str = config.get(CONF_XCOM_VOLTAGE_AC, config.get(CONF_VOLTAGE, DEFAULT_XCOM_VOLTAGE_AC))
        self._xcom_voltage_dc: str = config.get(CONF_XCOM_VOLTAGE_DC, DEFAULT_XCOM_VOLTAGE_DC)
        self._xcom_listen_port: int = config.get(CONF_XCOM_PORT, config.get(CONF_PORT, DEFAULT_XCOM_PORT))
        self._next_gw_host: str = config.get(CONF_NEXT_GW_HOST, DEFAULT_NEXT_GW_HOST)
        self._next_gw_port: str = config.get(CONF_NEXT_GW_PORT, DEFAULT_NEXT_GW_PORT)

        gateway_info_dict = config.get(CONF_GATEWAY_INFO, None) or config.get(CONF_CLIENT_INFO, {})
        self._gateway_info = StuderGatewayConfig.from_dict(gateway_info_dict)

        # Get devices from options (with fallback to config for backwards compatibility)
        devices_data = options.get(CONF_DEVICES, None) \
                    or config.get(CONF_DEVICES, [])
        self._devices: list[StuderDeviceConfig] = [StuderDeviceConfig.from_dict(d) for d in devices_data]

        # Api
        match self._product:
            case PRODUCTS.XCOM:
                self._api: AsyncStuderApi = AsyncXcomApiTcp(mode=XcomApiTcpMode.SERVER, listen_port=self._xcom_listen_port)
                self._object_id_base = StuderCoordinator.create_id(self._xcom_listen_port) # Base for object_id
                self._unique_id_base = StuderCoordinator.create_id(self._xcom_listen_port) # Base for internal unique_id (todo: set to client guid)
                self._device_id_base = StuderCoordinator.create_id(self._xcom_listen_port) # Base for device_id (todo: set to client guid)
                store_key = self._xcom_listen_port

            case PRODUCTS.NEXT:
                self._api: AsyncStuderApi = AsyncNextApi(host=self._next_gw_host, port=self._next_gw_port)
                self._object_id_base = StuderCoordinator.create_id(self._next_gw_host)      # Base for object_id
                self._unique_id_base = StuderCoordinator.create_id(self._gateway_info.guid) # Base for internal unique_id
                self._device_id_base = StuderCoordinator.create_id(self._gateway_info.guid) # Base for device_id
                store_key = self._next_gw_host

        # Id handling
        self._valid_unique_ids: dict[Platform, list[str]] = {}
        self._valid_device_ids: list[tuple[str,str]] = []

        # Coordinator data prepared for the entities
        self._entity_map: dict[str,StuderEntityData] = {}
        self._entity_map_ts = datetime.now()
        self.data = self._get_data()

        # Cached data to persist updated params saved into device RAM
        self._hass = hass
        self._store_key = StuderCoordinator.create_id(store_key)
        self._store = StuderCoordinatorStore(hass, self._store_key)
        self._cache = None
        self._cache_last_write = datetime.now()
        
        # Diagnostics gathering
        self._diag_requests = {}
        self._diag_statistics = {}


    def _get_data(self) -> dict[str, StuderEntityData]:
        return self._entity_map


    async def start(self) -> bool:
        self._entity_map: dict[str,StuderEntityData] = await self._create_entity_map()
        self._entity_map_ts = datetime.now()

        # Set initial data to construct the entities from     
        self.data = self._get_data()
        
        # Start our Api
        return await self._api.start()

    
    async def stop(self):

        # Write most recent values into the cache
        await self._async_persist_cache(force=True)
        
        # Stop our Api
        await self._api.stop()


    @property
    def is_connected(self) -> bool:
        return self._api.connected


    @property
    def config(self) -> dict[str,Any]:
        return self._config
    

    @property
    def options(self) ->dict[str,Any]:
        return self._options
    

    @property
    def is_temp(self) -> bool:
        return self._is_temp


    @property
    def product(self) -> PRODUCTS:
        return self._product


    @property
    def time_zone(self) -> tzinfo | None:
        return dt_util.get_time_zone(self._hass.config.time_zone)


    def set_valid_unique_ids(self, platform: Platform, ids: list[str]):
        self._valid_unique_ids[platform] = ids


    async def _create_entity_map(self):

        entity_map: dict[str,StuderEntityData] = {}

        # No need to load StuderDataset from file if no device numbers need resolving
        if not self._devices:
            return entity_map

        match self._product:
            case PRODUCTS.XCOM:
                # Load XcomDataset from file
                dataset = await XcomDataset.async_get_instance(self._xcom_voltage_ac, self._xcom_voltage_dc)
                families = await XcomDeviceFamilies.async_get_instance()

            case PRODUCTS.NEXT:
                # Load NextDataset from file(s)
                dataset = await NextDataset.async_get_instance()
                families = await NextDeviceFamilies.async_get_instance()

            case _:
                _LOGGER.warning(f"Unknown product '{self._product}' found during creation of entity map")

        # Resolve all numbers for each device
        for device in self._devices:
            family = families.get_by_id(device.family_id)
            family_id_for_nr = family.id_for_nr if hasattr(family, 'id_for_nr') else family.id

            for nr in device.numbers:
                try:
                    datapoint = dataset.get_by_nr(nr, family_id_for_nr)
                    entity = self._create_entity(datapoint, family, device)
                    if entity:
                        entity_map[entity.object_id] = entity

                except Exception as e:
                    _LOGGER.debug(f"Exception in _create_entity_map: {e}")

        return entity_map
    

    def _create_entity(self, datapoint: StuderDatapoint, family: StuderDeviceFamily, device: StuderDeviceConfig) -> StuderEntityData | None:
        try:
            # Store all properties for easy lookup by entities
            entity = StuderEntityData(
                datapoint = datapoint,

                object_id = StuderCoordinator.create_id(PREFIX_ID, self._object_id_base, device.code, datapoint.nr),
                unique_id = StuderCoordinator.create_id(PREFIX_ID, self._unique_id_base, device.code, datapoint.nr),

                # Device associated with this entity
                device_id = StuderCoordinator.create_id(PREFIX_ID, self._device_id_base, device.code),
                device_code = device.code,
                device_address = device.address,
            )
            return entity
        
        except Exception as e:
            _LOGGER.debug(f"Exception in _create_entity: {e}")
            return None
        

    async def async_create_devices(self, config_entry: ConfigEntry):
        """
        Add all detected devices to the hass device_registry
        """
        _LOGGER.debug(f"Create devices")
        dr = device_registry.async_get(self.hass)
        valid_ids: list[tuple[str,str]] = []

        for device in self._devices:
            device_id = StuderCoordinator.create_id(PREFIX_ID, self._device_id_base, device.code)
            _LOGGER.debug(f"Create device {device_id}")

            dr.async_get_or_create(
                config_entry_id = config_entry.entry_id,
                identifiers = {(DOMAIN, device_id)},
                name = f"{PREFIX_NAME} {device.code}",
                model = f"{device.family_model} {device.device_model or ''}",
                manufacturer =  MANUFACTURER,
                hw_version = str(device.hw_version) if device.hw_version is not None else None,
                sw_version = str(device.sw_version) if device.sw_version is not None else None,
                serial_number = str(device.serial) if device.serial is not None else None,
            )
            valid_ids.append( (DOMAIN, device_id) )
           
        # Remember valid device ids so we can do a cleanup of invalid ones later
        self._valid_device_ids = valid_ids


    async def async_cleanup_devices(self, config_entry: ConfigEntry):
        """
        cleanup all devices that are no longer in use
        """
        _LOGGER.info(f"Cleanup devices")

        dr = device_registry.async_get(self.hass)
        known_devices = device_registry.async_entries_for_config_entry(dr, config_entry.entry_id)

        for device in known_devices:
            if all(id not in self._valid_device_ids for id in device.identifiers):
                _LOGGER.info(f"Remove obsolete device {next(iter(device.identifiers))}")
                dr.async_remove_device(device.id)


    async def async_cleanup_entities(self, config_entry: ConfigEntry):
        """
        cleanup all entities that are no longer in use
        """
        _LOGGER.info(f"Cleanup entities")

        er = entity_registry.async_get(self.hass)
        known_entities = entity_registry.async_entries_for_config_entry(er, config_entry.entry_id)

        for entity in known_entities:
            # Note that platform and domain are mixed up in entity_registry
            valid_unique_ids = self._valid_unique_ids.get(entity.domain, [])

            if entity.unique_id not in valid_unique_ids:
                _LOGGER.info(f"Remove obsolete entity {entity.entity_id} ({entity.unique_id})")
                er.async_remove(entity.entity_id)


    async def _async_update_data(self):
        """
        Fetch sensor data from API.
        
        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        _LOGGER.debug(f"Update data")

        try:
            # Make sure the cache is available before we use it
            await self._async_read_cache()  

            # Request values for each configured param or infos number (datapoints). 
            # Note that a single (broadcasted) request can result in multiple reponses received 
            # (for instance in systems with more than one inverter)
            await self._async_request_all_data()

            # Periodically persist the cache
            await self._async_persist_cache()

            # return updated data
            return self._get_data()
            
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout while communicating with API: {err}")


    async def _async_request_all_data(self):
        """
        Send out requests to the remote gateway for each configured parameter or infos number.
        """
        diag_key = f"RequestValues"
        try:
            request_items: list[StuderValueItem] = [ StuderValueItem(datapoint=entity.datapoint, device=entity.device_code) for entity in self._entity_map.values() ]
            request_data = StuderValueSet(items = request_items)

            response_data = await self._api.request_values(request_data, retries=REQ_RETRIES, timeout=REQ_TIMEOUT)

            for item in response_data.items:
                # Find entity matching to this response item
                entity = next( (e for e in self._entity_map.values() if e.datapoint.nr == item.datapoint.nr and e.device_code == item.code), None)

                if entity is not None and item.value is not None:
                    self._entity_map[entity.object_id].value = item.value
                    self._entity_map[entity.object_id].valueModified = self._getModified(entity)
                    self._entity_map_ts = datetime.now()

            await self._addDiagnostic(diag_key, True)

        except Exception as e:
            if not isinstance(e, (XcomApiTimeoutException, NextApiTimeoutException)):
                _LOGGER.warning(f"Failed to request values from gateway: {e}")
            await self._addDiagnostic(diag_key, False, e)

    
    async def async_modify_data(self, entity: StuderEntityData, value, set_modified:bool=True):

        diag_key = f"UpdateValue {entity.device_code} {entity.datapoint.userlevel_w}"
        try:
            result = await self._api.update_value(entity.datapoint, value, device=entity.device_address)
            if result==True:
                _LOGGER.info(f"Successfully updated {entity.device_code} {entity.datapoint.nr} to value {value}")

                if set_modified and entity.value != value:
                    # Changed from its original (flash) value; remember as a modified_param
                    entity.valueModified = value
                    await self._setModified(entity, value)
                else:
                    # Reverted to its original (flash) value; remove from modified_param
                    entity.valueModified = None
                    await self._setModified(entity, None)

                await self._addDiagnostic(diag_key, True)
                return True
            
        except Exception as e:
            _LOGGER.warning(f"Failed to update value {entity.device_code} {entity.datapoint.nr}: {e}")
            await self._addDiagnostic(diag_key, False, e)

        return False
    

    async def async_get_message(self, index:int) -> dict:
        """"""
        match self._product:
            case PRODUCTS.XCOM:
                families = await XcomDeviceFamilies.async_get_instance()

            case PRODUCTS.NEXT:
                raise NotImplementedError(f"async_get_message is not implemented for product '{self._product}'")
            case _:
                raise ValueError(f"Unexpected value for 'product': '{self._product}'")

        diag_key = f"GetMessage"
        try:
            result = await self._api.request_message(index, retries=REQ_RETRIES, timeout=REQ_TIMEOUT)
            if result is not None:
                # Lookup code from addr within the available devices
                code = None
                for d in self._devices:
                    if (code := families.get_code_by_addr(result.source_address, d.family_id)) is not None:
                        break

                # Convert from StuderMessage to dict
                response = {
                    "message": result.message_string,
                    "source": code,
                    "timestamp": datetime.fromtimestamp(result.timestamp, timezone.utc).isoformat(),
                }
                if index==0:
                    response["total"] = result.message_total
                
                return response
            
        except Exception as e:
            _LOGGER.warning(f"Failed to get message {index}: {e}")
            await self._addDiagnostic(diag_key, False, e)

        return { "error": f"No message found for index {index}" }


    async def _async_read_cache(self):
        if self._is_temp:
            return
        
        if self._cache is not None:
            return  # already read
        
        if self._store:
            _LOGGER.debug(f"Read persisted cache")
            store = await self._store.async_get_data() or {}
            self._cache = store.get("cache", {})
        else:
            _LOGGER.warning(f"Using empty cache; no store available to read from")
            self._cache = {}


    async def _async_persist_cache(self, force: bool = False):
        if self._is_temp or self._cache is None:
            return
        
        if self._store:
            if force or (datetime.now() - self._cache_last_write).total_seconds() > CACHE_WRITE_PERIOD:
            
                _LOGGER.debug(f"Persist cache")
                self._cache_last_write = datetime.now()

                store = await self._store.async_get_data() or {}
                store["cache"] = self._cache
                await self._store.async_set_data(store)
        else:
            _LOGGER.warning(f"Skip persisting cache; no store available to write to")


    def _getModified(self, entity: StuderEntityData) -> Any:
        """
        Check if a modified param is available
        """
        if self._is_temp or self._cache is None:
            return None
        
        modified_params = self._cache.get(MODIFIED_PARAMS, {})

        return modified_params.get(entity.object_id, None)


    async def _setModified(self, entity: StuderEntityData, value: Any):
        """
        Remember a modified params value. Persist it in cache.
        """
        if self._is_temp or self._cache is None:
            return
        
        modified_params = self._cache.get(MODIFIED_PARAMS, {})

        if value is not None:
            modified_params[entity.object_id] = value
        else:
            modified_params.pop(entity.object_id, None)

        self._cache[MODIFIED_PARAMS] = modified_params
        self._cache[MODIFIED_PARAMS_TS] = datetime.now()

        # Trigger write of cache
        await self._async_persist_cache(force=True)

    
    async def _addDiagnostic(self, diag_key: str, success: bool, e: Exception|None = None):
        """
        Add a diagnostics statistic
        """
        diag_base = {
            "counters": {
                "success": 0,
                "fail_write": 0,
                "fail_read": 0,
                "fail_timout": 0,
                "fail_error": 0,
                "fail_unpack": 0,
                "fail_other": 0,
            },
            "errors": collections.OrderedDict()
        }
        stat_base = {
            "time": {
                "fail_hours": { h: 0 for h in range(0,24) },
                "fail_minutes": { m: 0 for m in range(0, 60, 5)},
            },
        }
        diag_data = diag_base | self._diag_requests.get(diag_key, {})
        stat_data = stat_base | self._diag_statistics
        ts = datetime.now()

        # Update per request diagnostics
        if success:
            diag_data["counters"]["success"] += 1
        else:
            if not e:                          diag_data["counters"]["fail_other"] += 1
            #AJH elif e is XcomApiConnectException: diag_data["counters"]["fail_connect"] += 1
            elif e is NextApiConnectException: diag_data["counters"]["fail_connect"] += 1
            elif e is XcomApiTimeoutException: diag_data["counters"]["fail_timeout"] += 1
            elif e is NextApiTimeoutException: diag_data["counters"]["fail_timeout"] += 1
            elif e is XcomApiReadException:    diag_data["counters"]["fail_read"] += 1
            elif e is NextApiReadException:    diag_data["counters"]["fail_read"] += 1
            elif e is XcomApiWriteException:   diag_data["counters"]["fail_write"] += 1
            elif e is NextApiUpdateException:  diag_data["counters"]["fail_write"] += 1
            elif e is XcomApiResponseIsError:  diag_data["counters"]["fail_error"] += 1
            elif e is XcomApiUnpackException:  diag_data["counters"]["fail_unpack"] += 1
            elif e is NextApiUnpackException:     diag_data["counters"]["fail_unpack"] += 1
            else:                              diag_data["counters"]["fail_other"] += 1

            if e:
                diag_data["errors"][str(ts)] = f"{str(e)} {type(e)}"

                while len(diag_data["errors"]) > 16:
                    diag_data["errors"].popitem(last=False)

        # Update overal statistics diagnostics
        if not success:
            stat_data["time"]["fail_hours"][ts.hour] += 1
            stat_data["time"]["fail_minutes"][ts.minute // 5 * 5] += 1

        # Remember these new values          
        self._diag_requests[diag_key] = diag_data
        self._diag_statistics = stat_data

    
    async def async_get_diagnostics(self) -> dict[str, Any]:
        entity_map = { k: v.__dict__ for k,v in self._entity_map.items() }
        diag_api = await self._api.get_diagnostics()

        return {
            "data": {
                "object_id_base": self._object_id_base,
                "unique_id_base": self._unique_id_base,
                "device_id_base": self._device_id_base,
                "entity_map_ts": str(self._entity_map_ts),
                "entity_map": entity_map,
            },
            "cache": self._cache,
            "diagnostics": {
                "requests": self._diag_requests,
                "statistics": self._diag_statistics | diag_api.get("statistics", {}),
            }
        },
    
    
    def address_to_code(self, address):
        """Convert a device address into a more user friendly device code"""
        return next( (d.code for d in self._devices if d.address == address), address)
    

    def timestamp_to_datetime(self, ts):
        """Convert a timestamp (seconds since 1-1-1970) into a datetime object"""
        if ts is None:
            return None
        
        ts_local = int(ts)
        dt_local = dt_util.utc_from_timestamp(ts_local).replace(tzinfo=self.time_zone)
        return dt_local
    

    def datetime_to_timestamp(self, dt):
        """Convert a datetime object into a timestamp (seconds since 1-1-1970)"""
        if dt is None:
            return None
        
        dt_local = dt.astimezone(self.time_zone)
        ts_local = dt_util.as_timestamp(dt_local.replace(tzinfo=timezone.utc))
        return int(ts_local)


    @staticmethod
    def create_id(*args):
        s = '_'.join(str(x) for x in args).strip('_')
        s = re.sub('[ -]', '_', s)
        s = re.sub('[^a-z0-9_]+', '', s.lower())
        return s        


class StuderDataError(Exception):

    """Exception to indicate generic data failure."""    


class StuderCoordinatorStore(Store[dict]):
    
    _STORAGE_VERSION_MAJOR = 1
    _STORAGE_VERSION_MINOR = 0
    _STORAGE_KEY = DOMAIN + ".coordinator"
    
    def __init__(self, hass, store_key):
        super().__init__(
            hass, 
            key=self._STORAGE_KEY, 
            version=self._STORAGE_VERSION_MAJOR, 
            minor_version=self._STORAGE_VERSION_MINOR
        )
        self._store_key = store_key

    
    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        """Migrate the history store data"""

        if old_major_version <= 1:
            # version 1 is the current version. No migrate needed
            data = old_data

        return data
    

    async def async_get_data(self):
        """Load the persisted coordinator_cache file and return the data specific for this coordinator instance"""
        data = await super().async_load() or {}
        data_self = data.get(self._store_key, {})
        return data_self
    

    async def async_set_data(self, data_self):
        """Save the data specific for this coordinator instance into the persisted coordinator_cache file"""
        data = await super().async_load() or {}
        data[self._store_key] = data_self
        await super().async_save(data)
    