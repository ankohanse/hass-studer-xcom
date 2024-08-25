##
# Definition of all known device families used in the Xcom protocol
##

import struct
import logging
from dataclasses import dataclass

from .xcom_const import (
    OBJ_TYPE,
)


_LOGGER = logging.getLogger(__name__)


class XcomDeviceFamilyUnknownException(Exception):
    pass

    
@dataclass
class XcomDeviceFamily:
    id: str
    idForNr: str
    model: str
    addrMulticast: int
    addrDevicesStart: int
    addrDevicesEnd: int
    nrParamsStart: int
    nrParamsEnd: int
    nrInfosStart: int
    nrInfosEnd: int
    nrDiscover: int
    nrDefaults: list[int]

    def get_code(self, addr):
        if addr == self.addrMulticast:
            return self.id.upper()
        
        if self.addrDevicesStart == addr == self.addrDevicesEnd:
            return self.id.upper()
        
        if self.addrDevicesStart <= addr <= self.addrDevicesEnd:
            idx = addr - self.addrDevicesStart + 1
            return f"{self.id.upper()}{idx}"
        
        _LOGGER.debug(f"Addr {addr} is not in range for family {self.id} addresses ({self.addrDevicesStart}-{self.addrDevicesEnd})")
        return None


class XcomDeviceFamilies:
    XTENDER = XcomDeviceFamily(
        "xt", "xt",
        "Xtender", 
        100,                   # addr multicast to all devices (write only)
        101, 115,              # addr devices,  start to end
        1000, 1999,            # nr for params, start to end
        3000, 3999,            # nr for infos,  start to end 
        3000,                  # nr for discovery
        [1107,3000,3007,3010,3028,3031,3032,3049,3078,3081,3083,3136,3137], # nr defaults setup during discovery
    )
    L1 = XcomDeviceFamily(
        "l1", "xt",
        "Phase L1", 
        191,                   # addr multicast to all devices (write only)
        191, 191,              # addr devices,  start to end
        1000, 1999,            # nr for params, start to end
        3000, 3999,            # nr for infos,  start to end   
        3000,                  # nr for discovery
        [], # nr defaults setup during discovery
    )
    L2 = XcomDeviceFamily(
        "l2", "xt",
        "Phase L2", 
        192,                   # addr multicast to all devices (write only)
        192, 192,              # addr devices,  start to end
        1000, 1999,            # nr for params, start to end
        3000, 3999,            # nr for infos,  start to end   
        3000,                  # nr for discovery
        [], # nr defaults setup during discovery
    )
    L3 = XcomDeviceFamily(
        "l3", "xt",
        "Phase L3", 
        193,                   # addr multicast to all devices (write only)
        193, 193,              # addr devices,  start to end
        1000, 1999,            # nr for params, start to end
        3000, 3999,            # nr for infos,  start to end   
        3000,                  # nr for discovery
        [], # nr defaults setup during discovery
    )
    RCC = XcomDeviceFamily(
        "rcc", "rcc",
        "RCC or Xcom-LAN", 
        501,                   # addr multicast to all devices (write only)
        501, 501,              # addr devices,  start to end
        5000, 5999,            # nr for params, start to end
        0, 0,                  # nr for infos,  start to end
        5002,                  # nr for discovery
        [5000], # nr defaults setup during discovery
    )
    BSP = XcomDeviceFamily(
        "bsp", "bsp",
        "BSP", 
        600,                   # addr multicast to all devices (write only)
        601, 601,              # addr devices,  start to end
        6000, 6999,            # nr for params, start to end
        7000, 7999,            # nr for infos,  start to end
        7036,                  # nr for discovery
        [7000,7001,7002,7003,7029], # nr defaults setup during discovery
    )
    BMS = XcomDeviceFamily(
        "bms", "bms",
        "Xcom-CAN BMS", 
        600,                   # addr multicast to all devices (write only)
        601, 601,              # addr devices,  start to end
        6000, 6999,            # nr for params, start to end
        7000, 7999,            # nr for infos,  start to end
        7054,                  # nr for discovery
        [7000,7001,7002,7003,7029], # nr defaults setup during discovery
    )
    VARIOTRACK = XcomDeviceFamily(
        "vt", "vt",
        "VarioTrack", 
        300,                   # addr multicast to all devices (write only)
        301, 315,              # addr devices,  start to end
        10000, 10999,          # nr for params, start to end
        11000, 11999,          # nr for infos,  start to end
        11000,                 # nr for discovery
        [11000,11001,11002,11003,11004,11007,11038,11069], # nr defaults setup during discovery
    )
    VARIOSTRING = XcomDeviceFamily(
        "vs", "vs",
        "VarioString", 
        700,                   # addr multicast to all devices (write only)
        701, 715,              # addr devices,  start to end
        14000, 14999,          # nr for params, start to end
        15000, 15999,          # nr for infos,  start to end
        15000,                 # nr for discovery
        [15000,15001,15002,15004,15007,15010,15017,15108], # nr defaults setup during discovery
    )

    @staticmethod
    def getById(id: str) -> XcomDeviceFamily:
        for f in XcomDeviceFamilies.getList():
            if id == f.id:
                return f

        raise XcomDeviceFamilyUnknownException(id)


    @staticmethod
    def getList() -> list[XcomDeviceFamily]:
        return [val for val in XcomDeviceFamilies.__dict__.values() if type(val) is XcomDeviceFamily]
