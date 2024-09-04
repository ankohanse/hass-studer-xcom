"""coordinator.py: responsible for gathering data."""

import asyncio
import async_timeout
import json
import logging
import re

from collections import namedtuple
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.components.light import LightEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.core import async_get_hass
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from homeassistant.const import (
    CONF_PORT, 
    CONF_DEVICES,
)

from .const import (
    DOMAIN,
    NAME,
    COORDINATOR,
    PREFIX_ID,
    PREFIX_NAME,
    CONF_VOLTAGE,
    CONF_POLLING_INTERVAL,
    DEFAULT_VOLTAGE,
    DEFAULT_PORT,
    DEFAULT_POLLING_INTERVAL,
)
from aioxcom import (
    XcomApiTcp,
    XcomApiWriteException,
    XcomApiReadException,
    XcomApiTimeoutException,
    XcomApiResponseIsError,
    XcomApiUnpackException,
    XcomDataset,
    XcomDatapoint,
    XcomDatapointUnknownException,
    XcomDeviceFamily,
    XcomDeviceFamilies,
    XcomDeviceFamilyUnknownException,
)


_LOGGER = logging.getLogger(__name__)

MODIFIED_PARAMS = "ModifiedParams"


class StuderDeviceConfig:
    def __init__(self, address, code, family_id, numbers):
        self.address = address
        self.code = code
        self.family_id = family_id
        self.numbers = numbers

    @staticmethod
    def from_dict(d: dict[str,Any]):
        return StuderDeviceConfig(
            d["address"],
            d["code"],
            d["family_id"],
            d["numbers"],
        )

    def as_dict(self) -> dict[str, Any]:
        """Return dictionary version of this device config."""
        return {
            "address": self.address,
            "code": self.code,
            "family_id": self.family_id,
            "numbers": self.numbers,
        }
    
    def __str__(self) -> str:
        return f"StuderDeviceConfig(address={self.address}, code={self.code}, family_id={self.family_id}, numbers={self.numbers})"

    def __repr__(self) -> str:
        return self.__str__()


class StuderEntity(XcomDatapoint):
    def __init__(self, param, object_id, unique_id, device_id, device_name, device_addr, device_model):
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

        # for StuderEntity
        self.object_id = object_id
        self.unique_id = unique_id
        self.weight = 1
        self.value = None
        self.valueModified = None

        self.device_id = device_id
        self.device_addr = device_addr
        self.device_name = device_name
        self.device_model = device_model


class StuderCoordinatorFactory:
    
    @staticmethod
    def create(hass: HomeAssistant, config_entry: ConfigEntry):
        """
        Get existing Coordinator for a config entry, or create a new one if it does not yet exist
        """
    
        # Get properties from the config_entry
        port = config_entry.data[CONF_PORT]
        config = config_entry.data
        options = config_entry.options

        if not COORDINATOR in hass.data[DOMAIN]:
            hass.data[DOMAIN][COORDINATOR] = {}
            
        # already created?
        coordinator = hass.data[DOMAIN][COORDINATOR].get(port, None)
        if not coordinator:
            # Get an instance of our coordinator. This is unique to this port
            coordinator = StuderCoordinator(hass, config, options)
            hass.data[DOMAIN][COORDINATOR][port] = coordinator
            
        return coordinator


    @staticmethod
    def create_temp(voltage, port):
        """
        Get temporary Coordinator for a given port.
        This coordinator will only provide limited functionality
        (connection test and device discovery)
        """
    
        # Get properties from the config_entry
        hass = async_get_hass()
        config: dict[str,Any] = {
            CONF_VOLTAGE: voltage,
            CONF_PORT: port,
            CONF_DEVICES: [],
        }
        options: dict[str,Any] = {}
        
        # Already have a coordinator for this port?
        coordinator = None
        if DOMAIN in hass.data and COORDINATOR in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][COORDINATOR].get(port, None)

        if not coordinator:
            # Get a temporary instance of our coordinator. This is unique to this port
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

        self._voltage: str = config.get(CONF_VOLTAGE, DEFAULT_VOLTAGE)
        self._port: int = config.get(CONF_PORT, DEFAULT_PORT)
        devices_data = config.get(CONF_DEVICES, [])

        self._devices: list[StuderDeviceConfig] = [StuderDeviceConfig.from_dict(d) for d in devices_data]
        self._options: dict[str,Any] = options

        self._api = XcomApiTcp(self._port)

        self._install_id = StuderCoordinator.create_id(self._port)
        self._entity_map: dict[str,StuderEntity] = self._create_entity_map()
        self._entity_map_ts = datetime.now()
        self.data = self._get_data()

        # Cached data to persist updated params saved into device RAM
        self._hass = hass
        self._store_key = self._install_id
        self._store = StuderCoordinatorStore(hass, self._store_key)
        self._modified_map: dict[str,Any] = {}
        self._modified_map_ts = datetime.now()
        
        # Diagnostics gathering
        self._diagnostics = {}


    def _get_data(self):
        return self._entity_map


    async def start(self) -> bool:
        self._modified_map = await self._async_fetch_from_cache(MODIFIED_PARAMS)
        self._modified_map_ts = datetime.now()

        return await self._api.start()

    
    async def stop(self):
        await self._api.stop()

    
    def is_connected(self) -> bool:
        return self._api.connected


    def _create_entity_map(self):
        entity_map: dict[str,StuderEntity] = {}

        dataset = XcomDataset.create(self._voltage)

        for device in self._devices:
            family = XcomDeviceFamilies.getById(device.family_id)

            for nr in device.numbers:
                try:
                    param = dataset.getByNr(nr, family.idForNr)
                    entity = self._create_entity(param, family, device)

                    entity_map[entity.object_id] = entity

                except Exception as e:
                    _LOGGER.debug(f"Exception in _create_entity_map: {e}")

        return entity_map
    

    def _create_entity(self, param: XcomDatapoint, family: XcomDeviceFamily, device: StuderDeviceConfig) -> StuderEntity | None:
    
        try:
            # Store all properties for easy lookup by entities
            entity = StuderEntity(
                param = param,

                object_id = StuderCoordinator.create_id(PREFIX_ID, self._install_id, device.code, param.nr),
                unique_id = StuderCoordinator.create_id(PREFIX_ID, self._install_id, device.code, param.nr),

                # Device associated with this entity
                device_id = StuderCoordinator.create_id(PREFIX_ID, self._install_id, device.code),
                device_name = f"{PREFIX_NAME} {device.code}",
                device_addr = device.address,
                device_model = family.model,
            )
            return entity
        
        except Exception as e:
            _LOGGER.debug(f"Exception in _create_entity: {e}")
            return None
        

    async def _async_update_data(self):
        """
        Fetch sensor data from API.
        
        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        _LOGGER.debug(f"Update data")

        try:
            # Request values for each configured param or infos number (datapoints). 
            # Note that a single (broadcasted) request can result in multiple reponses received 
            # (for instance in systems with more than one inverter)
            await self._async_request_all_data()

            # update cached data for diagnostics
            #await self._async_update_cache(f"entities", self._entity_map)

            # return updated data
            return self._get_data()
        
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout while communicating with API: {err}")


    async def _async_request_all_data(self):
        """
        Send out requests to the remote Xcom client for each configured parameter or infos number.
        """
        for entity in self._entity_map.values():

            diag_key = f"RequestValue {entity.device_name} {entity.level}"
            try:
                param = entity
                addr = entity.device_addr
            
                value = await self._api.requestValue(param, addr)
                if value is not None:
                    self._entity_map[entity.object_id].value = value
                    self._entity_map[entity.object_id].valueModified = self._getModified(entity)
                    self._entity_map_ts = datetime.now()

                    await self._addDiagnostic(diag_key, True)

            except Exception as e:
                if e is not XcomApiTimeoutException:
                    _LOGGER.warning(f"Failed to request value {entity.device_name} {entity.nr} from Xcom client: {e}")
                await self._addDiagnostic(diag_key, False, e)

    
    async def async_request_test(self, param, addr):
        try:
            value = await self._api.requestValue(param, addr)
            if value:
                return True
            
        except Exception as e:
            _LOGGER.debug(f"Failed to request test value from Xcom client: {e}")

        return False
    

    async def async_modify_data(self, entity: StuderEntity, value):

        diag_key = f"UpdateValue {entity.device_name} {entity.level}"
        modify_key = f"UpdateValue {entity.device_name} {entity.nr}"
        try:
            param = entity
            addr = entity.device_addr

            result = await self._api.updateValue(param, value, dstAddr=addr)
            if result==True:
                _LOGGER.info(f"Successfully updated {entity.device_name} {entity.nr} to value {value}")

                self._entity_map[entity.object_id].valueModified = value
                await self._addModified(entity, value)
                await self._addDiagnostic(diag_key, True)
                return True
            
        except Exception as e:
            _LOGGER.warning(f"Failed to update value {entity.device_name} {entity.nr} via Xcom client: {e}")
            await self._addDiagnostic(diag_key, False, e)

        return False


    async def _async_update_cache(self, context, data, force = False):
        # worker function
        async def _async_worker(self, context, data):
            if not self._store:
                return
            
            # Retrieve cache file contents
            store = await self._store.async_get_data() or {}
            cache = store.get("cache", {})

            data_old = cache.get(context, {})

            # We only update the cached contents once a day to prevent too many writes of unchanged data
            ts_str = data_old.get("ts", "")
            ts_old = datetime.fromisoformat(ts_str) if ts_str else datetime.min
            ts_new = datetime.now()

            if not force and (ts_new - ts_old).total_seconds() < 86400-300:   # 1 day minus 5 minutes
                # Not expired yet
                return

            _LOGGER.debug(f"Update cache: {context} to {data}")
        
            # Update and write new cache file contents
            cache[context] = { "ts": ts_new } | data
            
            store["cache"] = cache
            await self._store.async_set_data(store)

        # Create the worker task to update diagnostics in the background,
        # but do not let main loop wait for it to finish
        if self._hass:
            data["ts"] = datetime.now()
            self._hass.async_create_task(_async_worker(self, context, data))

    
    async def _async_fetch_from_cache(self, context):
        if not self._store:
            return {}
        
        store = await self._store.async_get_data() or {}
        cache = store.get("cache", {})
        data = cache.get(context, {})

        _LOGGER.debug(f"Fetch from cache: {context}, data: {data}")
        
        return data
    

    def _getModified(self, entity: StuderEntity) -> Any:
        return self._modified_map.get(entity.object_id, None)


    async def _addModified(self, entity: StuderEntity, value: Any):
        """
        Remember a modified params value. Persist it in cache.
        """
        self._modified_map[entity.object_id] = value
        self._modified_map_ts = datetime.now()

        await self._async_update_cache(MODIFIED_PARAMS, self._modified_map, force=True)

    
    async def _addDiagnostic(self, diag_key: str, success: bool, e: Exception|None = None):
        """
        Add a diagnostics statistic
        """
        diag_data = self._diagnostics.get(diag_key, None)
        if not diag_data:
            diag_data = {
                "counters": {
                    "success": 0,
                    "fail_write": 0,
                    "fail_read": 0,
                    "fail_timout": 0,
                    "fail_error": 0,
                    "fail_unpack": 0,
                    "fail_other": 0,
                },
                "last_errors": [],
                "last_error_ts": None,
            }

        if success:
            diag_data["counters"]["success"] += 1
        else:
            if not e:
                diag_data["counters"]["fail_other"] += 1
            elif e is XcomApiWriteException:
                diag_data["counters"]["fail_write"] += 1
            elif e is XcomApiReadException:
                diag_data["counters"]["fail_read"] += 1
            elif e is XcomApiTimeoutException:
                diag_data["counters"]["fail_timeout"] += 1
            elif e is XcomApiResponseIsError:
                diag_data["counters"]["fail_error"] += 1
            elif e is XcomApiUnpackException:
                diag_data["counters"]["fail_unpack"] += 1
            else:
                diag_data["counters"]["fail_other"] += 1

            if e:
                diag_data["last_error_ts"] = str(datetime.now())
                diag_data["last_errors"].append(str(e))

                while len(diag_data["last_errors"]) > 16:
                    diag_data["last_errors"].pop(0)

        self._diagnostics[diag_key] = diag_data

    
    async def async_get_diagnostics(self) -> dict[str, Any]:
        entity_map = { k: v.__dict__ for k,v in self._entity_map.items() }

        return {
            "data": {
                "install_id": self._install_id,
                "entity_map_ts": str(self._entity_map_ts),
                "entity_map": entity_map,
                "modified_map_ts": str(self._modified_map_ts),
                "modified_map": self._modified_map,
            },
            "diagnostics": self._diagnostics,
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
    