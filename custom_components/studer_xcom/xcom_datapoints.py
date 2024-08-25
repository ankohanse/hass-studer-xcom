#! /usr/bin/env python3

##
# Definition of all parameters / constants used in the Xcom protocol
##

import json
import logging
import struct

from dataclasses import dataclass
from pathlib import Path

from homeassistant.util.json import json_loads_array

from .xcom_const import (
    LEVEL,
    FORMAT,
    OBJ_TYPE,
)


_LOGGER = logging.getLogger(__name__)


class XcomDatapointUnknownException(Exception):
    pass


@dataclass
class XcomDatapoint:
    family: str
    level: LEVEL
    parent: int | None
    nr: int
    name: str
    abbr: str   # abbreviated/coded name
    unit: str
    format: FORMAT
    default: float = None
    min: float = None
    max: float = None
    inc: float = None
    options: dict = None

    @staticmethod
    def from_dict(d):
        fam = d.get('fam', None)
        lvl = d.get('lvl', None)
        pnr = d.get('pnr', None)
        nr  = d.get('nr', None)
        name = d.get('name', None)
        abbr = d.get('short', None)
        unit = d.get('unit', None)
        fmt = d.get('fmt', None)
        dft = d.get('def', None)
        min = d.get('min', None)
        max = d.get('max', None)
        inc = d.get('inc', None)
        opt = d.get('opt', None)

        # Check and convert properties
        if not fam or not lvl or not nr or not name or not fmt:
            return None
        
        if type(pnr) is not int:
            return None

        if type(nr) is not int:
            return None

        lvl = LEVEL.from_str(lvl)
        fmt = FORMAT.from_str(fmt)
        
        name = str(name).strip()
        dft = float(dft) if (type(dft) is int or type(dft) is float) else None
        min = float(min) if (type(min) is int or type(min) is float) else None
        max = float(max) if (type(max) is int or type(max) is float) else None
        inc = float(inc) if (type(inc) is int or type(inc) is float) else None
            
        return XcomDatapoint(fam, lvl, pnr, nr, name, abbr, unit, fmt, dft, min, max, inc, opt)
        
    @property
    def obj_type(self):
        if self.level in [LEVEL.INFO]:
            return OBJ_TYPE.INFO

        if self.level in [LEVEL.BASIC, LEVEL.EXPERT, LEVEL.INST, LEVEL.QSP]:
            return OBJ_TYPE.PARAMETER
            
        _LOGGER.debug(f"Unknown obj_type for datapoint {self.nr} with level {self.level} and format {self.format}")
        return OBJ_TYPE.INFO


class XcomDatasetFactory:

    @staticmethod
    def create():
        """
        The actual XcomDataset list is kept in a separate json file to reduce the memory size needed to load the integration.
        The list is only loaded during config flow and during initial startup, and then released again.
        """
        path = Path(__file__.replace('.py', '.json'))
        text = path.read_text(encoding="UTF-8")
        values = json_loads_array(text)

        # transform into list of XcomDatapoint objects
        datapoints: list[XcomDatapoint] = []
        for val in values:
            datapoint = XcomDatapoint.from_dict(val)
            if datapoint:
                datapoints.append(datapoint)

        return XcomDataset(datapoints)
    

class XcomDataset:

    def __init__(self, datapoints: list[XcomDatapoint] | None = None):
        self._datapoints = datapoints
   

    def getByNr(self, nr: int, family: str|None = None) -> XcomDatapoint:
        for point in self._datapoints:
            if point.nr == nr and (point.family == family or family is None):
                return point

        raise XcomDatapointUnknownException(id, family)
    

    def getMenuItems(self, parent: int = 0, family: str|None = None):
        datapoints = []
        for point in self._datapoints:
            if point.parent == parent and (point.family == family or family is None):
                datapoints.append(point)

        return datapoints

