"""Constants for the Studer Xcom integration."""

import logging

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

_LOGGER: logging.Logger = logging.getLogger(__package__)

# Base component constants
DOMAIN = "studer_xcom"
NAME = "Studer Xcom"
ISSUE_URL = "https://github.com/ankohanse/hass-studer-xcom/issues"

STARTUP_MESSAGE = f"""
----------------------------------------------------------------------------
{NAME}
Domain: {DOMAIN}
----------------------------------------------------------------------------
"""

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

HUB = "Hub"
API = "Api"
COORDINATOR = "Coordinator"
HELPER = "Helper"

# configuration items and their defaults
VOLTAGE_120VAC = "120 Vac"
VOLTAGE_240VAC = "240 Vac"

DEFAULT_VOLTAGE = VOLTAGE_240VAC
DEFAULT_PORT = 4001
DEFAULT_USER_LEVEL = "INFO"
DEFAULT_POLLING_INTERVAL = 30

DEFAULT_FAMILY_NUMBERS = {
    "xt": [3020,3028,3031,3032,3049,3078,3081,3083,3101,3104,3119],
    "l1": [],
    "l2": [],
    "l3": [],
    "rcc": [],
    "bsp": [7007,7008,7030,7031,7032,7033],
    "bms": [7007,7008,7030,7031,7032,7033],
    "vt": [11007,11025,11038,11039,11040,11041,11042,11045,11069],
    "vs": [15017,15030,15054,15057,15064,15065,15108],
}

CONF_VOLTAGE = "voltage"
CONF_USER_LEVEL = "user_level"
CONF_OPTIONS = "options"
CONF_POLLING_INTERVAL = "polling_interval"

#Entity configuration
CONF_NR = "nr"
CONF_ADDRESS = "address"
MSG_POLLING_INTERVAL = 'polling_interval'

# To compose entity unique id and names
MANUFACTURER = "Studer"
PREFIX_ID = "studer"
PREFIX_NAME = "Studer"

# Custom extra attributes to entities
ATTR_XCOM_FLASH_STATE = "xcom_flash_state"
ATTR_XCOM_RAM_STATE = "xcom_ram_state"

# Used to recognize a binary_sensor from a regular sensor
BINARY_SENSOR_VALUES_ON = [1, True, '1', 'on', 'On']
BINARY_SENSOR_VALUES_OFF = [0, False, '0', 'off', 'Off']
BINARY_SENSOR_VALUES_ALL = BINARY_SENSOR_VALUES_ON + BINARY_SENSOR_VALUES_OFF

# Used to recognized a switch instead of a select
SWITCH_VALUES_ON = [1, True, '1', 'On']
SWITCH_VALUES_OFF = [0, False, '0', 'Off']
SWITCH_VALUES_ALL = SWITCH_VALUES_ON + SWITCH_VALUES_OFF

# Request retries
REQ_TIMEOUT = 3
REQ_RETRIES = 3

# Diagnostics
DIAGNOSTICS_REDACT = { 'conf_secret1', 'conf_secret2' }
