"""xcom_api.py: communication api to Studer Xcom via LAN."""

import asyncio

import contextlib
import logging
import socket

from concurrent.futures import ThreadPoolExecutor
from io import BufferedWriter, BytesIO

from .xcom_const import (
    FORMAT,
    OBJ_TYPE,
    SCOM_OBJ_TYPE,
    SCOM_SERVICE,
    SCOM_QSP_ID,
    SCOM_ERROR_CODES,
)
from .xcom_protocol import (
    XcomPackage,
    XcomHeader,
    XcomFrame,
    XcomData,
    XcomDataMultiInfoReq,
    XcomDataMultiInfoReqItem,
    XcomDataMultiInfoRsp,
    XcomDataMultiInfoRspItem,
    XcomDataMessageRsp,
    checksum,
)
from .xcom_datapoints import (
    XcomDatapoint,
    XcomDataset,
    XcomDatapointUnknownException,
)

from .xcom_families import (
    XcomDeviceFamilies
)

from .const import (
    DEFAULT_PORT,
)

_LOGGER = logging.getLogger(__name__)


MSG_HEADER_LENGTH = 14
MSG_MAX_LENGTH = 256

##
## Class abstracting Xcom-LAN TCP network protocol
##
class XcomAPi:

    def __init__(self, port=DEFAULT_PORT):
        """
        MOXA is connecting to the TCP Server we are creating here.
        Once it is connected we can send package requests.
        """
        self.localPort = port
        self._server = None
        self._reader = None
        self._writer = None
        self._started = False
        self._connected = False


    async def start(self):
        _LOGGER.info(f"Starting Xcom TCP server on port {self.localPort}")

        self._server = await asyncio.start_server(self._client_connected_cb, "0.0.0.0", self.localPort, limit=1000, family=socket.AF_INET, reuse_port=True, )
        self._server._start_serving()
        self._started = True

        _LOGGER.info("Waiting for Xcom TCP client to connect...")
        return self


    async def stop(self):
        _LOGGER.info(f"Stopping Xcom TCP server")
        try:
            self._connected = False

            # Close the writer; we do not need to close the reader
            if self._writer:
                self._writer.close()
    
        except Exception as e:
            _LOGGER.warning(f"Exception during closing of Xcom writer: {e}")

        # Close the server
        try:
            async with asyncio.timeout(5):
                if self._server:
                    self._server.close()
                    await self._server.wait_closed()
    
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            _LOGGER.warning(f"Exception during closing of Xcom server: {e}")

        self._started = False
        _LOGGER.info(f"Stopped Xcom TCP server")
    

    @property
    def connected(self):
        return self._connected
    

    async def _client_connected_cb(self, reader, writer):
        self._reader = reader
        self._writer = writer
        self._connected = True

        peername = self._writer.get_extra_info("peername")
        _LOGGER.info(f"Connected to Xcom client '{peername}'")


    async def requestValue(self, parameter: XcomDatapoint, dstAddr = None):
        
        # Compose the request and send it
        request: XcomPackage = XcomPackage.genPackage(
            service_id = SCOM_SERVICE.READ,
            object_type = SCOM_OBJ_TYPE.fromObjType(parameter.obj_type),
            object_id = parameter.nr,
            property_id = SCOM_QSP_ID.VALUE,
            property_data = XcomData.NONE,
            dst_addr = dstAddr
        )
        response = await self._sendPackage(request, timeout=3)

        # Check the response
        if not response:
            return None

        if response.isError():
            # Any other error response we will just log, but we also stop waiting for a next response
            msg = SCOM_ERROR_CODES.getByData(response.frame_data.service_data.property_data)
            _LOGGER.debug(f"Response package for {parameter.nr}:{dstAddr} states error: '{msg}'")
            return None

        # Unpack the response value
        return XcomData.unpack(response.frame_data.service_data.property_data, parameter.format)


    async def requestValues(self, props: list[tuple[XcomDatapoint, int | None]]):
        """
        Method does not work, results in a 'Service not supported' response
        """
        prop = XcomDataMultiInfoReq()
        for (parameter, dstAddr) in props:
            prop.append(XcomDataMultiInfoReqItem(parameter.nr, 0x00))

        # Compose the request and send it
        request: XcomPackage = XcomPackage.genPackage(
            service_id = SCOM_SERVICE.READ,
            object_type = SCOM_OBJ_TYPE.MULTI_INFO,
            object_id = 0x01020304,
            property_id = SCOM_QSP_ID.VALUE,
            property_data = prop.getBytes(),
            dst_addr = 101
        )
        await self._sendPackage(request)


    async def updateValue(self, parameter: XcomDatapoint, value, dstAddr = 100):

        # Sanity check: the parameter/datapoint must have obj_type == OBJ_TYPE.PARAMETER
        if parameter.obj_type != OBJ_TYPE.PARAMETER:
            _LOGGER.warn(f"Ignoring attempt to update readonly infos value {parameter}")
            return

        _LOGGER.debug(f"Update value {parameter} on addr {dstAddr}")

        request: XcomPackage = XcomPackage.genPackage(
            service_id = SCOM_SERVICE.WRITE,
            object_type = SCOM_OBJ_TYPE.PARAMETER,
            object_id = parameter.nr,
            property_id = SCOM_QSP_ID.UNSAVED_VALUE,
            property_data = XcomData.pack(value, parameter.format),
            dst_addr = dstAddr
        )
        response = await self._sendPackage(request, timeout=3)

        # Check the response
        if not response:
            return None

        if response.isError():
            # Any other error response we will just log, but we also stop waiting for a next response
            msg = SCOM_ERROR_CODES.getByData(response.frame_data.service_data.property_data)
            _LOGGER.debug(f"Response package for {parameter.nr}:{dstAddr} states error: '{msg}'")
            return False

        # Success
        _LOGGER.info(f"Successfully updated value {parameter} on addr {dstAddr}")
        return True


    async def _sendPackage(self, request: XcomPackage, timeout=3) -> XcomPackage | None:
        if not self._connected:
            _LOGGER.info(f"_sendPackage - not connected")
            return None
        
        # Send the request package to the Xcom client
        try:
            #_LOGGER.debug(f"send {request}")
            self._writer.write(request.getBytes())

        except Exception as e:
            _LOGGER.warning(f"Exception while sending request package to Xcom client: {e}")
            return None

        # Receive packages until we get the one we expect
        try:
            async with asyncio.timeout(timeout):
                while True:
                    response = await XcomPackage.parse(self._reader)

                    if response.isResponse() and \
                       response.frame_data.service_id == request.frame_data.service_id and \
                       response.frame_data.service_data.object_id == request.frame_data.service_data.object_id and \
                       response.frame_data.service_data.property_id == request.frame_data.service_data.property_id:

                        # Yes, this is the answer to our request
                        #_LOGGER.debug(f"recv {response}")
                        return response
                    
                    else:
                        # No, not an answer to our request, continue loop for next answer (or timeout)
                        pass

        except asyncio.TimeoutError:
            pass

        except Exception as e:
            _LOGGER.warning(f"Exception while listening for response package from Xcom client: {e}")

        return None



