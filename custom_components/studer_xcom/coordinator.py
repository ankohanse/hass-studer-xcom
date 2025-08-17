"""coordinator.py: responsible for gathering data."""

import asyncio
import collections
import logging
import re

from collections import namedtuple
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

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
    DOMAIN,
    NAME,
    MANUFACTURER,
    COORDINATOR,
    PREFIX_ID,
    PREFIX_NAME,
    CONF_VOLTAGE,
    CONF_POLLING_INTERVAL,
    DEFAULT_VOLTAGE,
    DEFAULT_PORT,
    DEFAULT_POLLING_INTERVAL,
    REQ_RETRIES,
    REQ_TIMEOUT,
    REQ_BURST_SIZE,
    CACHE_WRITE_PERIOD,
)
from aioxcom import (
    XcomApiTcp,
    XcomApiWriteException,
    XcomApiReadException,
    XcomApiTimeoutException,
    XcomApiResponseIsError,
    XcomApiUnpackException,
    XcomDiscoveredClient,
    XcomDiscoveredDevice,
    XcomDataset,
    XcomDatapoint,
    XcomDatapointUnknownException,
    XcomDeviceFamily,
    XcomDeviceFamilies,
    XcomDeviceFamilyUnknownException,
)


_LOGGER = logging.getLogger(__name__)

MODIFIED_PARAMS = "ModifiedParams"
MODIFIED_PARAMS_TS = "ModifiedParamsTs"


class StuderClientConfig(XcomDiscoveredClient):
    def __init__(self, ip, mac):
        # From XcomDiscoveredClient
        self.ip = ip
        self.mac = device_registry.format_mac(mac) if mac else None

    @staticmethod
    def from_dict(d: dict[str,Any]):
        return StuderClientConfig(
            d.get("ip", None),
            d.get("mac", None),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this client info."""
        return {
            "ip": self.ip,
            "mac": self.mac,
        }
    
    def __str__(self) -> str:
        return f"StuderClientConfig(ip={self.ip}, mac={self.mac})"

    def __repr__(self) -> str:
        return self.__str__()


class StuderDeviceConfig(XcomDiscoveredDevice):
    def __init__(self, code, addr, family_id, family_model, device_model, hw_version, sw_version, fid, numbers):
        # From XcomDiscoveredDevice
        self.code = code
        self.addr = addr
        self.family_id = family_id
        self.family_model = family_model
        self.device_model = device_model
        self.hw_version = hw_version
        self.sw_version = sw_version
        self.fid = fid

        # For StuderDeviceConfig
        self.numbers = numbers

    @staticmethod
    def match(a, b):
        if not isinstance(a, XcomDiscoveredDevice) or not isinstance(b, XcomDiscoveredDevice):
            return False
        
        # Either match code or match addr and family_id
        if a.code == b.code:
            return True
        if a.addr == b.addr and a.family_id == b.family_id:
            return True
        
        return False

    @staticmethod
    def from_dict(d: dict[str,Any]):
        return StuderDeviceConfig(
            d["code"],
            d["address"],
            d["family_id"],
            d["family_model"],
            d["device_model"],
            d["hw_version"],
            d["sw_version"],
            d["fid"],
            d["numbers"],
        )

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this device config."""
        return {
            "code": self.code,
            "address": self.addr,
            "family_id": self.family_id,
            "family_model": self.family_model,
            "device_model": self.device_model,
            "hw_version": self.hw_version,
            "sw_version": self.sw_version,
            "fid": self.fid,
            "numbers": self.numbers,
        }
    
    def __str__(self) -> str:
        return f"StuderDeviceConfig(code={self.code}, family_id={self.family_id}, address={self.addr}, numbers={self.numbers})"

    def __repr__(self) -> str:
        return self.__str__()


class StuderEntityData(XcomDatapoint):
    def __init__(self, param, object_id, unique_id, device_id, device_code, device_addr):
        # from XcomDatapoint
        self.family_id = param.family_id
        self.level = param.level
        self.parent = param.parent
        self.nr = param.nr
        self.name = param.name
        self.abbr = param.abbr
        self.unit = param.unit
        self.format = param.format
        self.default = param.default
        self.min = param.min
        self.max = param.max
        self.inc = param.inc
        self.options = param.options

        # for StuderEntityData
        self.object_id = object_id
        self.unique_id = unique_id
        self.weight = 1
        self.value = None
        self.valueModified = None

        self.device_id = device_id
        self.device_code = device_code
        self.device_addr = device_addr


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
    async def async_create_temp(voltage, port):
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
            CONF_VOLTAGE: voltage,
            CONF_PORT: port,
        }
        options: dict[str,Any] = {
            CONF_DEVICES: [],
        }
        
        # Already have a coordinator for this port and voltage?
        coordinator = next( 
            (c for c in hass.data[DOMAIN][COORDINATOR].values() if c.config.get(CONF_PORT, None)==port and c.config.get(CONF_VOLTAGE, None)==voltage), 
            None
        )

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

        self._voltage: str = config.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)
        self._port: int = config.get(CONF_PORT, DEFAULT_PORT)

        # Get devices from options (with fallback to config for backwards compatibility)
        devices_data = options.get(CONF_DEVICES, None) \
                    or config.get(CONF_DEVICES, [])
        self._devices: list[StuderDeviceConfig] = [StuderDeviceConfig.from_dict(d) for d in devices_data]

        self._api = XcomApiTcp(self._port)

        # Id handling
        self._object_id_base = StuderCoordinator.create_id(self._port) # Base for object_id
        self._unique_id_base = StuderCoordinator.create_id(self._port) # Base for internal unique_id (todo: set to client MAC)
        self._device_id_base = StuderCoordinator.create_id(self._port) # Base for device_id (todo: set to client MAC)
        self._valid_unique_ids: dict[Platform, list[str]] = {}
        self._valid_device_ids: list[tuple[str,str]] = []

        # Coordinator data prepared for the entities
        self._entity_map: dict[str,StuderEntityData] = {}
        self._entity_map_ts = datetime.now()
        self.data = self._get_data()

        # Cached data to persist updated params saved into device RAM
        self._hass = hass
        self._store_key = StuderCoordinator.create_id(self._port)
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
    def time_zone(self) -> tzinfo | None:
        return dt_util.get_time_zone(self._hass.config.time_zone)


    def set_valid_unique_ids(self, platform: Platform, ids: list[str]):
        self._valid_unique_ids[platform] = ids


    async def _create_entity_map(self):

        entity_map: dict[str,StuderEntityData] = {}

        # No need to load XcomDataset from file if no device numbers need resolving
        if not self._devices:
            return entity_map

        # Load XcomDataset from file
        dataset = await XcomDataset.create(self._voltage)

        # Resolve all numbers for each device
        for device in self._devices:
            family = XcomDeviceFamilies.getById(device.family_id)

            for nr in device.numbers:
                try:
                    param = dataset.getByNr(nr, family.idForNr)
                    entity = self._create_entity(param, family, device)
                    if entity:
                        entity_map[entity.object_id] = entity

                except Exception as e:
                    _LOGGER.debug(f"Exception in _create_entity_map: {e}")

        return entity_map
    

    def _create_entity(self, param: XcomDatapoint, family: XcomDeviceFamily, device: StuderDeviceConfig) -> StuderEntityData | None:
    
        try:
            # Store all properties for easy lookup by entities
            entity = StuderEntityData(
                param = param,

                object_id = StuderCoordinator.create_id(PREFIX_ID, self._object_id_base, device.code, param.nr),
                unique_id = StuderCoordinator.create_id(PREFIX_ID, self._unique_id_base, device.code, param.nr),

                # Device associated with this entity
                device_id = StuderCoordinator.create_id(PREFIX_ID, self._device_id_base, device.code),
                device_code = device.code,
                device_addr = device.addr,
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
            family = XcomDeviceFamilies.getById(device.family_id)
            device_id = StuderCoordinator.create_id(PREFIX_ID, self._device_id_base, device.code)

            _LOGGER.debug(f"Create device {device_id}")

            dr.async_get_or_create(
                config_entry_id = config_entry.entry_id,
                identifiers = {(DOMAIN, device_id)},
                name = f"{PREFIX_NAME} {device.code}",
                model = f"{family.model} {device.device_model or ''}",
                manufacturer =  MANUFACTURER,
                hw_version = device.hw_version,
                sw_version = device.sw_version,
                serial_number = device.fid,
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
        Send out requests to the remote Xcom client for each configured parameter or infos number.
        """
        for i, entity in enumerate(self._entity_map.values()):

            diag_key = f"RequestValue {entity.device_code} {entity.level}"
            try:
                param = entity
                addr = entity.device_addr
            
                value = await self._api.requestValue(param, addr, retries=REQ_RETRIES, timeout=REQ_TIMEOUT)
                if value is not None:
                    self._entity_map[entity.object_id].value = value
                    self._entity_map[entity.object_id].valueModified = self._getModified(entity)
                    self._entity_map_ts = datetime.now()

                    await self._addDiagnostic(diag_key, True)

            except Exception as e:
                if e is not XcomApiTimeoutException:
                    _LOGGER.warning(f"Failed to request value {entity.device_code} {entity.nr} from Xcom client: {e}")
                await self._addDiagnostic(diag_key, False, e)

            # Periodically wait for a second. This will make sure we do not block Xcom-LAN with
            # too many requests at once and prevent it from uploading data to the Studer portal.
            if i % REQ_BURST_SIZE == 0:
                await asyncio.sleep(1)

    
    async def async_modify_data(self, entity: StuderEntityData, value, set_modified:bool=True):

        diag_key = f"UpdateValue {entity.device_code} {entity.level}"
        try:
            param = entity
            addr = entity.device_addr

            result = await self._api.updateValue(param, value, dstAddr=addr)
            if result==True:
                _LOGGER.info(f"Successfully updated {entity.device_code} {entity.nr} to value {value}")

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
            _LOGGER.warning(f"Failed to update value {entity.device_code} {entity.nr} via Xcom client: {e}")
            await self._addDiagnostic(diag_key, False, e)

        return False


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
            elif e is XcomApiWriteException:   diag_data["counters"]["fail_write"] += 1
            elif e is XcomApiReadException:    diag_data["counters"]["fail_read"] += 1
            elif e is XcomApiTimeoutException: diag_data["counters"]["fail_timeout"] += 1
            elif e is XcomApiResponseIsError:  diag_data["counters"]["fail_error"] += 1
            elif e is XcomApiUnpackException:  diag_data["counters"]["fail_unpack"] += 1
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
        diag_api = await self._api.getDiagnostics()

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
    

    @staticmethod
    def create_id(*args):
        s = '_'.join(str(x) for x in args).strip('_')
        s = re.sub(' ', '_', s)
        s = re.sub('[^a-z0-9_-]+', '', s.lower())
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
    