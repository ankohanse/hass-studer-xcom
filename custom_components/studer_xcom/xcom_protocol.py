##
## Class implementing Xcom protocol 
##
## See the studer document: "Technical Specification - Xtender serial protocol"
## Download from:
##   https://studer-innotec.com/downloads/ 
##   -> Downloads -> software + updates -> communication protocol xcom 232i
##


import logging
import struct
from io import BufferedWriter, BufferedReader, BytesIO

from .xcom_const import (
    FORMAT,
    SCOM_OBJ_TYPE,
    SCOM_ERROR_CODES,
)

_LOGGER = logging.getLogger(__name__)


class XcomData:
    NONE = b''

    @staticmethod
    def unpack(value: bytes, format):
        match format:
            case FORMAT.BOOL: return struct.unpack("<?", value)[0]          # 1 byte, little endian, bool
            case FORMAT.ERROR: return struct.unpack("<H", value)[0]         # 2 bytes, little endian, unsigned short/int16
            case FORMAT.FORMAT: return struct.unpack("<H", value)[0]        # 2 bytes, little endian, unsigned short/int16
            case FORMAT.SHORT_ENUM: return struct.unpack("<H", value)[0]    # 2 bytes, little endian, unsigned short/int16
            case FORMAT.FLOAT: return struct.unpack("<f", value)[0]         # 4 bytes, little endian, float
            case FORMAT.INT32: return struct.unpack("<i", value)[0]         # 4 bytes, little endian, signed long/int32
            case FORMAT.LONG_ENUM: return struct.unpack("<I", value)[0]     # 4 bytes, little endian, unsigned long/int32
            case FORMAT.STRING: return value.decode('iso-8859-15')          # n bytes, ISO_8859-15 string of 8 bit characters
            case _: raise TypeError("Unknown data format '{format}")

    @staticmethod
    def pack(value, format) -> bytes:
        match format:
            case FORMAT.BOOL: return struct.pack("<?", int(value))               # 1 byte, little endian, bool
            case FORMAT.SHORT_ENUM: return struct.pack("<H", int(value))         # 2 bytes, little endian, unsigned short/int16
            case FORMAT.FLOAT: return struct.pack("<f", float(value))              # 4 bytes, little endian, float
            case FORMAT.INT32: return struct.pack("<i", int(value))              # 4 bytes, little endian, signed long/int32
            case FORMAT.LONG_ENUM: return struct.pack("<I", int(value))          # 4 bytes, little endian, unsigned long/int32
            case FORMAT.STRING: return value.encode('iso-8859-15')         # n bytes, ISO_8859-15 string of 8 bit characters
            case _: raise TypeError("Unknown data format '{format}")

    @staticmethod
    def cast(value: float, format):
        match format:
            case FORMAT.BOOL: return bool(value)
            case FORMAT.ERROR: return int(value)
            case FORMAT.FORMAT: return int(value)
            case FORMAT.SHORT_ENUM: int(value)
            case FORMAT.FLOAT: return value
            case FORMAT.INT32: return int(value)
            case FORMAT.LONG_ENUM: return int(value)
            case FORMAT.STRING: return value.decode('iso-8859-15') 
            case _: raise TypeError(f"Unknown data format '{format}")


class XcomDataMultiInfoReqItem():
    user_info_ref: int
    aggregation_type: int

    def __init__(self, user_info_ref: int, aggregation_type: int):
        self.user_info_ref = user_info_ref
        self.aggregation_type = aggregation_type


class XcomDataMultiInfoReq:
    items: list[XcomDataMultiInfoReqItem]

    def __init__(self):
        self.items = list()

    def append(self, item: XcomDataMultiInfoReqItem):
        self.items.append(item)

    def assemble(self, f: BufferedWriter):
        _LOGGER.debug(f"XcomDataMultiInfoReq assemble {len(self.items)} items")
        for item in self.items:
            writeUInt16(f, item.user_info_ref)
            writeUInt8(f, item.aggregation_type)

    def getBytes(self) -> bytes:
        buf = BytesIO()
        self.assemble(buf)
        return buf.getvalue()

    def __len__(self) -> int:
        return 3 * len(self.items)

    def __str__(self) -> str:
        return f"(len={len(self.items)})"


class XcomDataMultiInfoRspItem():
    user_info_ref: int
    aggregation_type: int
    value: float

    def __init__(self, user_info_ref: int, aggregation_type: int, value: float):
        self.user_info_ref = user_info_ref
        self.aggregation_type = aggregation_type
        self.value = value


class XcomDataMultiInfoRsp:
    flags: int
    datetime: int
    items: list[XcomDataMultiInfoRspItem]

    @staticmethod
    def parse(f: BufferedReader, len: int):
        flags = readUInt32(f)
        datetime= readUInt32(f)
        items = list()

        while len >= 7:
            item = XcomDataMultiInfoRspItem()
            item.user_info_ref = readUInt16(f)
            item.aggregation_type = readUInt8(f)
            item.value = readFloat(f)
            len = len - 7

            items.append(item)

        return XcomDataMultiInfoRsp(flags, datetime, items)
    
    @staticmethod
    def parseBytes(buf: bytes):
        bio = BytesIO(buf)
        return XcomDataMultiInfoRsp.parse(bio, bio.getbuffer().nbytes)    
        
    def __init__(self, flags, datetime, items):
        flags = None
        datetime = None
        items = list()

    def __len__(self) -> int:
        return 2*4 + len(self.items)*(2+1+4)

    def __str__(self) -> str:
        return f"(flags={self.flags}, datetime={self.datetime}, len={len(self.items)})"


class XcomDataMessageRsp:
    msg_total: int      # 4 bytes
    msg_type: int       # 2 bytes
    src: int            # 4 bytes
    timestamp: int      # 4 bytes
    value: bytes        # 4 bytes

    @staticmethod
    def parse(f: BufferedReader):
        msg_total = readUInt32(f)
        msg_type= readUInt16(f)
        src = readUInt32(f)
        timestamp = readUInt32(f)
        value = f.read(4)

        return XcomDataMessageRsp(msg_total, msg_type, src, timestamp, value)
    
    @staticmethod
    def parseBytes(buf: bytes):
        return XcomDataMessageRsp.parse(BytesIO(buf))  
        
    def __init__(self, msg_total, msg_type, src, timestamp, value):
        self.msg_total = msg_total
        self.msg_type = msg_type
        self.src = src
        self.timestamp = timestamp
        self.value = value

    def __len__(self) -> int:
        return 2*4 + len(self.items)*(2+1+4)

    def __str__(self) -> str:
        return f"(flags={self.flags}, datetime={self.datetime}, len={len(self.items)})"


class XcomService:

    object_type: bytes
    object_id: int
    property_id: bytes
    property_data: bytes

    @staticmethod
    def parse(f: BufferedReader):
        return XcomService(
            f.read(2),
            readUInt32(f),
            f.read(2),
            f.read(-1),
        )

    def __init__(self, 
            object_type: bytes, object_id: int, 
            property_id: bytes, property_data: bytes):

        assert len(object_type) == 2
        assert len(property_id) == 2

        self.object_type = object_type
        self.object_id = object_id
        self.property_id = property_id
        self.property_data = property_data

    def assemble(self, f: BufferedWriter):
        f.write(self.object_type)
        writeUInt32(f, self.object_id)
        f.write(self.property_id)
        f.write(self.property_data)

    def __len__(self) -> int:
        return 2*2 + 4 + len(self.property_data)

    def __str__(self) -> str:
        return f"(obj_type={self.object_type.hex()}, obj_id={self.object_id}, property_id={self.property_id.hex()}, property_data={self.property_data.hex(' ',1)})"

class XcomFrame:

    service_flags: int
    service_id: bytes
    service_data: XcomService

    @staticmethod
    def parse(f: BufferedReader):
        return XcomFrame(
            service_flags = readUInt8(f),
            service_id = f.read(1),
            service_data = XcomService.parse(f)
        )

    @staticmethod
    def parseBytes(buf: bytes):
        return XcomFrame.parse(BytesIO(buf))

    def __init__(self, service_id: bytes, service_data: XcomService, service_flags=0):
        assert service_flags >= 0, "service_flag must not be negative"
        assert len(service_id) == 1

        self.service_flags = service_flags
        self.service_id = service_id
        self.service_data = service_data

    def assemble(self, f: BufferedWriter):
        writeUInt8(f, self.service_flags)
        f.write(self.service_id)
        self.service_data.assemble(f)

    def getBytes(self) -> bytes:
        buf = BytesIO()
        self.assemble(buf)
        return buf.getvalue()

    def __len__(self) -> int:
        return 2*1 + len(self.service_data)

    def __str__(self) -> str:
        return f"Frame(flags={self.service_flags}, id={self.service_id.hex()}, service={self.service_data})"

class XcomHeader:

    frame_flags: int
    src_addr: int
    dst_addr: int
    data_length: int

    length: int = 2*4 + 2 + 1

    @staticmethod
    def parse(f: BufferedReader):
        return XcomHeader(
            frame_flags=readUInt8(f),
            src_addr=readUInt32(f),
            dst_addr=readUInt32(f),
            data_length=readUInt16(f)
        )

    @staticmethod
    def parseBytes(buf: bytes):
        return XcomHeader.parse(BytesIO(buf))

    def __init__(self, src_addr: int, dst_addr: int, data_length: int, frame_flags=0):
        assert frame_flags >= 0, "frame_flags must not be negative"

        self.frame_flags = frame_flags
        self.src_addr = src_addr
        self.dst_addr = dst_addr
        self.data_length = data_length

    def assemble(self, f: BufferedWriter):
        writeUInt8(f, self.frame_flags)
        writeUInt32(f, self.src_addr)
        writeUInt32(f, self.dst_addr)
        writeUInt16(f, self.data_length)

    def getBytes(self) -> bytes:
        buf = BytesIO()
        self.assemble(buf)
        return buf.getvalue()

    def __len__(self) -> int:
        return self.length

    def __str__(self) -> str:
        return f"Header(flags={self.frame_flags}, src={self.src_addr}, dst={self.dst_addr}, data_length={self.data_length})"

class XcomPackage:

    start_byte: bytes = b'\xAA'
    header: XcomHeader
    frame_data: XcomFrame

    @staticmethod
    async def parse(f: BufferedReader):
        # package sometimes starts with 0xff
        skip = 0
        raw_sb = b''
        while raw_sb != XcomPackage.start_byte:
            raw_sb = await f.read(1)
            skip += 1

        if skip > 1:
            _LOGGER.debug(f"skipped {skip} bytes until start_byte")

        h_raw = await f.read(XcomHeader.length)
        assert checksum(h_raw) == await f.read(2)
        header = XcomHeader.parseBytes(h_raw)

        f_raw = await f.read(header.data_length)
        assert checksum(f_raw) == await f.read(2)
        frame = XcomFrame.parseBytes(f_raw)

        return XcomPackage(header, frame)

    @staticmethod
    def parseBytes(buf: bytes):
        return XcomPackage.parse(BytesIO(buf))

    @staticmethod
    def genPackage(service_id: bytes,
            object_type: bytes,
            object_id: int,
            property_id: bytes,
            property_data: bytes,
            src_addr = 1,
            dst_addr = 0):
        
        service = XcomService(object_type, object_id, property_id, property_data)
        frame = XcomFrame(service_id, service)
        header = XcomHeader(src_addr, dst_addr, len(frame))

        return XcomPackage(header, frame)


    def __init__(self, header: XcomHeader, frame_data: XcomFrame):
        self.header = header
        self.frame_data = frame_data

    def assemble(self, f: BufferedWriter):
        f.write(self.start_byte)

        header = self.header.getBytes()
        f.write(header)
        f.write(checksum(header))

        data = self.frame_data.getBytes()
        f.write(data)
        f.write(checksum(data))

    def getBytes(self) -> bytes:
        buf = BytesIO()
        self.assemble(buf)
        return buf.getvalue()

    def isResponse(self) -> bool:
        return (self.frame_data.service_flags & 2) >> 1 == 1

    def isError(self) -> bool:
        return self.frame_data.service_flags & 1 == 1

    def getError(self) -> str:
        if self.isError():
            return SCOM_ERROR_CODES.get(
                self.frame_data.service_data.property_data,
                "UNKNOWN ERROR"
            )
        return None
 
    def __str__(self) -> str:
        return f"Package(header={self.header}, frame_data={self.frame_data})"

##

def checksum(data: bytes) -> bytes:
    """Function to calculate the checksum needed for the header and the data"""
    A = 0xFF
    B = 0x00

    for d in data:
        A = (A + d) % 0x100
        B = (B + A) % 0x100

    A = struct.pack("<B", A)
    B = struct.pack("<B", B)

    return A + B

##

def readFloat(f: BufferedReader) -> float:
    return float.from_bytes(f.read(4), byteorder="little", signed=True)


def readUInt32(f: BufferedReader) -> int:
    return int.from_bytes(f.read(4), byteorder="little", signed=False)

def writeUInt32(f: BufferedWriter, value: int) -> int:
    return f.write(value.to_bytes(4, byteorder="little", signed=False))

def readSInt32(f: BufferedReader) -> int:
    return int.from_bytes(f.read(4), byteorder="little", signed=True)

def writeSInt32(f: BufferedWriter, value: int) -> int:
    return f.write(value.to_bytes(4, byteorder="little", signed=True))


def readUInt16(f: BufferedReader) -> int:
    return int.from_bytes(f.read(2), byteorder="little", signed=False)

def writeUInt16(f: BufferedWriter, value: int) -> int:
    return f.write(value.to_bytes(2, byteorder="little", signed=False))


def readUInt8(f: BufferedReader) -> int:
    return int.from_bytes(f.read(1), byteorder="little", signed=False)

def writeUInt8(f: BufferedWriter, value: int) -> int:
    return f.write(value.to_bytes(1, byteorder="little", signed=False))
