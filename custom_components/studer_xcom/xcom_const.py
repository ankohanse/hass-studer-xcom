#! /usr/bin/env python3

##
# Definition of all parameters / constants used in the Xcom protocol
##

import enum
import struct
from dataclasses import dataclass
from enum import IntEnum, StrEnum


@dataclass
class ValueTuple:
    id: int
    value: str

    def __eq__(self, __o: object) -> bool:
        if __o.__class__ is self.__class__:
            return __o.id == self.id
        return __o == self.id

    def __ne__(self, __o: object) -> bool:
        if __o.__class__ is self.__class__:
            return __o.id != self.id
        return __o != self.id

    def __str__(self) -> str:
        return self.value


### data types
class LEVEL(IntEnum):
    INFO   = 0x0000
    BASIC  = 0x0010
    EXPERT = 0x0020
    INST   = 0x0030 # Installer
    QSP    = 0x0040 # Qualified Service Person
    VO     = 0xFFFF # View Only? Used for param 5012, marked as 'not supported'

    @staticmethod
    def from_str(s: str):
        match s.upper():
            case 'INFO': return LEVEL.INFO
            case 'BASIC': return LEVEL.BASIC
            case 'EXPERT': return LEVEL.EXPERT
            case 'INST' | 'INST.': return LEVEL.INST
            case 'QSP': return LEVEL.QSP
            case 'VO' | 'V.O.': return LEVEL.VO
            case _: raise Exception(f"Unknown level: '{s}'")

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

class FORMAT(StrEnum):
    BOOL       = "BOOL"         # 1 byte
    FORMAT     = "FORMAT"       # 2 bytes
    SHORT_ENUM = "SHORT ENUM"   # 2 bytes
    ERROR      = "ERROR"        # 2 bytes
    INT32      = "INT32"        # 4 bytes
    FLOAT      = "FLOAT"        # 4 bytes
    LONG_ENUM  = "LONG_ENUM"    # 4 bytes
    STRING     = "STRING"       # n bytes
    DYNAMIC    = "DYNAMIC"      # n bytes
    BYTES      = "BYTES"        # n bytes
    MENU       = "MENU"         # n.a.
    INVALID    = "INVALID"      # n.a.

    @staticmethod
    def from_str(s: str):
        match s.upper():
            case 'BOOL': return FORMAT.BOOL
            case 'FORMAT': return FORMAT.FORMAT
            case 'SHORT_ENUM' | 'SHORT ENUM': return FORMAT.SHORT_ENUM
            case 'ERROR': return FORMAT.ERROR
            case 'INT32': return FORMAT.INT32
            case 'FLOAT': return FORMAT.FLOAT
            case 'LONG_ENUM' | 'LONG ENUM': return FORMAT.LONG_ENUM
            case 'STRING': return FORMAT.STRING
            case 'DYNAMIC': return FORMAT.DYNAMIC
            case 'BYTES': return FORMAT.BYTES
            case 'MENU' | 'ONLY_LEVEL' | 'ONLY LEVEL': return FORMAT.MENU
            case 'NOT SUPPORTED': return FORMAT.INVALID
            case _: raise Exception(f"Unknown format: '{s}'")

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

### object_type
class OBJ_TYPE(StrEnum):
    INFO       = "INFO"
    PARAMETER  = "PARAMETER"
    MESSAGE    = "MESSAGE"
    GUID       = "GUID"
    DATALOG    = "DATALOG"

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

    @staticmethod
    def fromScomObjType(obj_type):
        match obj_type:
            case SCOM_OBJ_TYPE.INFO: return OBJ_TYPE.INFO
            case SCOM_OBJ_TYPE.PARAMETER: return OBJ_TYPE.PARAMETER
            case SCOM_OBJ_TYPE.MESSAGE: return OBJ_TYPE.MESSAGE
            case SCOM_OBJ_TYPE.GUID: return OBJ_TYPE.GUID
            case SCOM_OBJ_TYPE.DATALOG: return OBJ_TYPE.DATALOG
            case _: raise Exception(f"Unknown obj_type: '{obj_type}'")

### object_type in Scom/Xcom
class SCOM_OBJ_TYPE:
    MULTI_INFO = b'\x00\x0A'
    INFO       = b'\x01\x00'
    PARAMETER  = b'\x02\x00'
    MESSAGE    = b'\x03\x00'
    GUID       = b'\x04\x00'
    DATALOG    = b'\x05\x00'

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

    @staticmethod
    def fromObjType(obj_type):
        match obj_type:
            case OBJ_TYPE.INFO: return SCOM_OBJ_TYPE.INFO
            case OBJ_TYPE.PARAMETER: return SCOM_OBJ_TYPE.PARAMETER
            case OBJ_TYPE.MESSAGE: return SCOM_OBJ_TYPE.MESSAGE
            case OBJ_TYPE.GUID: return SCOM_OBJ_TYPE.GUID
            case OBJ_TYPE.DATALOG: return SCOM_OBJ_TYPE.DATALOG
            case _: raise Exception(f"Unknown obj_type: '{obj_type}'")

### service_id
class SCOM_SERVICE:
    READ   = b'\x01'
    WRITE  = b'\x02'

### property_id
class SCOM_QSP_ID:
    VALUE           = b'\x05\x00'
    MIN             = b'\x06\x00'
    MAX             = b'\x07\x00'
    LEVEL           = b'\x08\x00'
    UNSAVED_VALUE   = b'\x0D\x00'

## values for QSP_LEVEL
class SCOM_QSP_LEVEL:
    VIEW_ONLY       = b'\x00\x00'
    BASIC           = b'\x10\x00'
    EXPERT          = b'\x20\x00'
    INSTALLER       = b'\x30\x00'
    QSP             = b'\x40\x00'

## values for aggregation_type
class SCOM_AGGREGATION_TYPE:
    MASTER          = b'\x00'
    DEVICE1         = b'\x01'
    DEVICE2         = b'\x02'
    DEVICE3         = b'\x03'
    DEVICE4         = b'\x04'
    DEVICE5         = b'\x05'
    DEVICE6         = b'\x06'
    DEVICE7         = b'\x07'
    DEVICE8         = b'\x08'
    DEVICE9         = b'\x09'
    DEVICE10        = b'\x0A'
    DEVICE11        = b'\x0B'
    DEVICE12        = b'\x0C'
    DEVICE13        = b'\x0D'
    DEVICE14        = b'\x0E'
    DEVICE15        = b'\x0F'
    AVERAGE         = b'\xFD'
    SUM             = b'\xFE'

# SCOM_ADDRESSES
SCOM_ADDR_BROADCAST = 0

### operating modes (11016)
MODE_NIGHT      = ValueTuple(0, "MODE_NIGHT")
MODE_STARTUP    = ValueTuple(1, "MODE_STARTUP")
MODE_CHARGER    = ValueTuple(3, "MODE_CHARGER")
MODE_SECURITY   = ValueTuple(5, "MODE_SECURITY")
MODE_OFF        = ValueTuple(6, "MODE_OFF")
MODE_CHARGE     = ValueTuple(8, "MODE_CHARGE")
MODE_CHARGE_V   = ValueTuple(9, "MODE_CHARGE_V")
MODE_CHARGE_I   = ValueTuple(10, "MODE_CHARGE_I")
MODE_CHARGE_T   = ValueTuple(11, "MODE_CHARGE_T")

MODE_CHARGING = (
    MODE_CHARGE,
    MODE_CHARGE_V,
    MODE_CHARGE_I,
    MODE_CHARGE_T
)

### battey cycle phase (11038)
PHASE_BULK      = ValueTuple(0, "PHASE_BULK")
PHASE_ABSORPT   = ValueTuple(1, "PHASE_ABSORPT")
PHASE_EQUALIZE  = ValueTuple(2, "PHASE_EQUALIZE")
PHASE_FLOATING  = ValueTuple(3, "PHASE_FLOATING")
PHASE_R_FLOAT   = ValueTuple(6, "PHASE_R_FLOAT")
PHASE_PER_ABS   = ValueTuple(7, "PHASE_PER_ABS")


### error codes
class SCOM_ERROR_CODES:
    NO_ERROR                                = b'\x00\x00' 
    INVALID_FRAME                           = b'\x01\x00' 
    DEVICE_NOT_FOUND                        = b'\x02\x00' 
    RESPONSE_TIMEOUT                        = b'\x03\x00' 
    SERVICE_NOT_SUPPORTED                   = b'\x11\x00' 
    INVALID_SERVICE_ARGUMENT                = b'\x12\x00' 
    SCOM_ERROR_GATEWAY_BUSY                 = b'\x13\x00' 
    TYPE_NOT_SUPPORTED                      = b'\x21\x00' 
    OBJECT_ID_NOT_FOUND                     = b'\x22\x00' 
    PROPERTY_NOT_SUPPORTED                  = b'\x23\x00' 
    INVALID_DATA_LENGTH                     = b'\x24\x00' 
    PROPERTY_IS_READ_ONLY                   = b'\x25\x00' 
    INVALID_DATA                            = b'\x26\x00' 
    DATA_TOO_SMALL                          = b'\x27\x00' 
    DATA_TOO_BIG                            = b'\x28\x00' 
    WRITE_PROPERTY_FAILED                   = b'\x29\x00' 
    READ_PROPERTY_FAILED                    = b'\x2A\x00' 
    ACCESS_DENIED                           = b'\x2B\x00' 
    SCOM_ERROR_OBJECT_NOT_SUPPORTED         = b'\x2C\x00' 
    SCOM_ERROR_MULTICAST_READ_NOT_SUPPORTED = b'\x2D\x00' 
    OBJECT_PROPERTY_INVALID                 = b'\x2E\x00' 
    FILE_OR_DIR_NOT_PRESENT                 = b'\x2F\x00' 
    FILE_CORRUPTED                          = b'\x30\x00' 
    INVALID_SHELL_ARG                       = b'\x81\x00'

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name

    @staticmethod
    def getByData(data: bytes):
        for key,val in SCOM_ERROR_CODES.__dict__.items():
            if type(key) is str and type(val) is bytes and val==data:
                return key

        return f"unknown {data.hex()}"
