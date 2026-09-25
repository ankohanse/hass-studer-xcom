"""Constants for the Studer Xcom integration."""

import logging

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

from pystuderxcom import (
    StuderUserLevel,
    XcomVoltage,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)

# Base component constants
DOMAIN = "studer_xcom"
NAME = "Studer Xcom"
ISSUE_URL = "https://github.com/ankohanse/hass-studer-xcom/issues"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.DATETIME,
    Platform.TIME,
]

XCOM_TITLE_FMT  = "Studer via Xcom port {port}"
NEXT_TITLE_FMT  = "Studer via Next Gateway {host}"

HUB = "Hub"
COORDINATOR = "Coordinator"

class PRODUCTS(StrEnum):
    XCOM = "xcom"
    NEXT = "next"


# configuration items and their defaults
DEFAULT_PRODUCT = PRODUCTS.XCOM
DEFAULT_XCOM_VOLTAGE_AC = XcomVoltage.AC240
DEFAULT_XCOM_VOLTAGE_DC = XcomVoltage.DC48
DEFAULT_XCOM_PORT = 4001
DEFAULT_NEXT_GW_HOST = ""
DEFAULT_NEXT_GW_PORT = 502
DEFAULT_USER_LEVEL = StuderUserLevel.BASIC
DEFAULT_POLLING_INTERVAL = 30

DEFAULT_XCOM_FAMILY_NUMBERS = {
    "xt": [3020,3028,3031,3032,3049,3078,3081,3083,3101,3104,3119],
    "l1": [],
    "l2": [],
    "l3": [],
    "rcc": [5002,5012],
    "bsp": [7007,7008,7030,7031,7032,7033],
    "bms": [7007,7008,7030,7031,7032,7033],
    "vt": [11007,11025,11038,11039,11040,11041,11043,11045,11069],
    "vs": [15017,15030,15054,15057,15064,15065,15108],
    "xcom": [99020,99022],
}
DEFAULT_NEXT_FAMILY_NUMBERS = {
    "sys": [3908,3924,7505,7519,8400,8410,8422,8426],
    "bat": [318,320,326,329,342,344,346],
    "acs": [0,2,6,8,24,36,1815],
    "flx": [],
    "nx1": [2700,2702,3001,3107,3301,3307],
    "nx3": [5100,5102,6900,6902,8101,8107,8401,8407],
    "nxg": [4500],
    "pwr": [300,302,304,324,326,328],
    "tst": [840,841,842,843,844]
}

DEFAULT_PRODUCT_FAMILY_NUMBERS = {
    PRODUCTS.XCOM: DEFAULT_XCOM_FAMILY_NUMBERS,
    PRODUCTS.NEXT:    DEFAULT_NEXT_FAMILY_NUMBERS,
}

CONF_PRODUCT = "product"
CONF_XCOM_VOLTAGE_AC = "voltage_ac"
CONF_XCOM_VOLTAGE_DC = "voltage_dc"
CONF_XCOM_PORT = "xcom_port"
CONF_XCOM_WEBCONFIG_URL = "xcom_webconfig_url"
CONF_NEXT_GW_HOST = "next_gw_host"
CONF_NEXT_GW_PORT = "next_gw_port"
CONF_NEXT_WEBCONFIG_URL = "next_webconfig_url"
CONF_GATEWAY_INFO = "gateway_info"
CONF_USER_LEVEL = "user_level"
CONF_OPTIONS = "options"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_VOLTAGE = "voltage"    # depricated, replaced by CONF_VOLTAGE_AC
CONF_WEBCONFIG_URL = "webconfig_url"      # depricated, replaced by CONF_XCOM_WEBCONFIG_URL
CONF_CLIENT_INFO = "client_info" # depricates, replaced by CONF_GATEWAY_INFO

INTEGRATION_README_URL = "https://github.com/ankohanse/hass-studer-xcom/blob/master/README.md"
XCOM_README_URL = "https://github.com/ankohanse/hass-studer-xcom/blob/master/Xcom-LAN%20config.md"
XCOM_APPENDIX_URL = "https://github.com/ankohanse/pystuderxcom/blob/master/documentation/Technical%20specification%20-%20Xtender%20serial%20protocol%20appendix%20-%201.6.38.pdf"
NEXT_README_URL = "https://github.com/ankohanse/hass-studer-xcom/blob/master/NextGateway%20config.md"
NEXT_MODBUS_APPENDIX_URL = "https://github.com/ankohanse/pystudernext/blob/master/documentation/Technical%20specification%20%E2%80%93%20Next%20Modbus%20appendix%20v10.73.pdf"

PRODUCTS_README_URL = {
    PRODUCTS.XCOM: XCOM_README_URL,
    PRODUCTS.NEXT: NEXT_README_URL,
}
PRODUCTS_NUMBERS_URL = {
    PRODUCTS.XCOM: XCOM_APPENDIX_URL,
    PRODUCTS.NEXT: NEXT_MODBUS_APPENDIX_URL,
}

#Entity configuration
CONF_NR = "nr"
CONF_ADDRESS = "address"
MSG_POLLING_INTERVAL = 'polling_interval'

# To compose entity unique id and names
MANUFACTURER = "Studer"
PREFIX_ID = "studer"
PREFIX_NAME = "Studer"

# Custom extra attributes to entities, displayed in the UI
ATTR_STUDER_STATE = "studer_state"
ATTR_STUDER_FLASH_STATE = "studer_flash_state"
ATTR_STUDER_RAM_STATE = "studer_ram_state"

# Extra attributes that are restored from the previous HA run
ATTR_STORED_VALUE = "value"
ATTR_STORED_VALUE_MODIFIED = "value_modified"

# Used to recognize a binary_sensor from a regular sensor
BINARY_SENSOR_VALUES_ON = [1, True, '1', 'on', 'On']
BINARY_SENSOR_VALUES_OFF = [0, False, '0', 'off', 'Off']
BINARY_SENSOR_VALUES_ALL = BINARY_SENSOR_VALUES_ON + BINARY_SENSOR_VALUES_OFF

# Used to recognized a switch instead of a select
SWITCH_VALUES_ON = [1, True, '1', 'On']
SWITCH_VALUES_OFF = [0, False, '0', 'Off']
SWITCH_VALUES_ALL = SWITCH_VALUES_ON + SWITCH_VALUES_OFF

# Request retries
REQ_TIMEOUT = 3 # seconds
REQ_RETRIES = 3 
CACHE_WRITE_PERIOD = 60*60 # seconds

# Diagnostics
DIAGNOSTICS_REDACT = { 'conf_secret1', 'conf_secret2' }
