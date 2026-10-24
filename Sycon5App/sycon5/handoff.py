"""The SYCON.net handoff folder PL5 writes (`SyconNetProjectInterface/`): three csv files with a contract-v1
`#!openn` header - hw/sycon-stations (SyconStations.csv), hw/sycon-modules (SyconModules.csv),
hw/sycon-device-types (SyconDeviceTypesDatabase.csv). Read by position (the `#` header line documents the
columns), like OP5 reads the TIA kinds.
"""
import csv
import os
import re
from dataclasses import dataclass, field

STATIONS_FILE, MODULES_FILE, DTD_FILE = "SyconStations.csv", "SyconModules.csv", "SyconDeviceTypesDatabase.csv"
STATION_KEYS = ["role", "station_name", "catalog_kind", "catalog_item", "model_id", "gsdml", "ip_address",
                "subnet_mask", "gateway", "update_time_ms", "device_number", "description", "comment",
                "symbolic_name", "fld"]
MODULE_KEYS = ["station_name", "slot", "subslot", "module_id", "module_text", "parameters", "comment"]
# the columns added on 2026-10-23 (key -> the words the `#` column line carries when the column is there): an
# older export without them is read by its own positions
OPTIONAL_STATION_KEYS = {"gsdml": "gsdml", "update_time_ms": "update time",
                         "symbolic_name": "symbolic", "fld": "fld"}       # the two of 2026-10-24: the canvas, BusField
OPTIONAL_MODULE_KEYS = {"subslot": "subslot"}


def natural_key(name):
    """A natural sort key of a station name: its digit runs as numbers (n0005-... < n0010-... < n0100-...,
    sm006 < sm011) - user 2026-10-24: the devices of a type in the project "sorted naturally by profinet name"."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(name or "").lower())]


def keys_for(all_keys, optional, columns_line):
    names = (columns_line or "").lower()
    return [k for k in all_keys if k not in optional or optional[k] in names]


class HandoffError(ValueError):
    pass


def parse_parameters(text):
    """'0=1 | 2=0.4 ms | potential_group=Enable new potential group (light BaseUnit)' -> [(name, value), ...]."""
    out = []
    for part in str(text or "").split("|"):
        if "=" not in part:
            if part.strip():
                raise HandoffError("parameter without '=': %r" % part)
            continue
        name, _, value = part.partition("=")
        out.append((name.strip(), value.strip()))
    return out


def read_headed_csv(path):
    """(header dict, data rows) of a `#!openn` csv: the directives between `#!openn` and `#!end`, the `#` comment
    lines dropped (the first one, the column line, kept as head["columns"]), Excel's trailing delimiters tolerated."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()
    head, body, in_header = {}, [], False
    for ln in lines:
        s = ln.strip().rstrip(",;").strip()
        if s == "#!openn":
            in_header = True
            continue
        if s == "#!end":
            in_header = False
            continue
        if in_header:
            if s.startswith("#!"):
                k, _, v = s[2:].partition(":")
                head[k.strip()] = v.strip()
            continue
        if not ln.strip():
            continue
        if ln.lstrip().startswith("#"):
            head.setdefault("columns", ln.lstrip().lstrip("#").strip())
            continue
        body.append(ln)
    delimiter = ";" if body and body[0].count(";") > body[0].count(",") else ","
    rows = [[c.strip() for c in r] for r in csv.reader(body, delimiter=delimiter)]
    return head, rows


@dataclass
class Handoff:
    folder: str
    controller: dict
    stations: list                      # slave / gateway rows in file order
    modules: dict = field(default_factory=dict)      # station name -> [module rows in slot order]
    headers: dict = field(default_factory=dict)

    def module_rows(self, station):
        """Every row of the station: the module rows (no subslot) and the submodule rows (slot + subslot)."""
        return self.modules.get(station, [])

    def plug_rows(self, station):
        return [m for m in self.module_rows(station) if not m.get("subslot")]

    def submodule_rows(self, station):
        """The submodule rows to PLUG (a slot of the station's own modules, never the DAP's slot 0)."""
        return [m for m in self.module_rows(station) if m.get("subslot") and m["slot"] != "0"]

    def dap_rows(self, station):
        """The rows of the device's own submodules (slot 0, e.g. a switch's PN-IO): parameters and records only."""
        return [m for m in self.module_rows(station) if m.get("subslot") and m["slot"] == "0"]


def load_handoff(folder):
    spath, mpath = os.path.join(folder, STATIONS_FILE), os.path.join(folder, MODULES_FILE)
    if not os.path.exists(spath):
        raise HandoffError("no %s in %s" % (STATIONS_FILE, folder))
    sh, srows = read_headed_csv(spath)
    if sh.get("kind") != "hw/sycon-stations":
        raise HandoffError("%s is not hw/sycon-stations (kind %r)" % (spath, sh.get("kind")))
    keys = keys_for(STATION_KEYS, OPTIONAL_STATION_KEYS, sh.get("columns", ""))
    stations = [dict(zip(keys, r + [""] * len(keys))) for r in srows if r and r[0]]
    for s in stations:
        for k in OPTIONAL_STATION_KEYS:
            s.setdefault(k, "")
    controllers = [s for s in stations if s["role"] == "controller"]
    if len(controllers) != 1:
        raise HandoffError("%d controller rows in %s (one expected)" % (len(controllers), spath))
    modules, mh = {}, {}
    if os.path.exists(mpath):
        mh, mrows = read_headed_csv(mpath)
        if mh.get("kind") != "hw/sycon-modules":
            raise HandoffError("%s is not hw/sycon-modules (kind %r)" % (mpath, mh.get("kind")))
        mkeys = keys_for(MODULE_KEYS, OPTIONAL_MODULE_KEYS, mh.get("columns", ""))
        for r in mrows:
            if not r or not r[0]:
                continue
            m = dict(zip(mkeys, r + [""] * len(mkeys)))
            for k in OPTIONAL_MODULE_KEYS:
                m.setdefault(k, "")
            modules.setdefault(m["station_name"], []).append(m)
    return Handoff(folder=folder, controller=controllers[0],
                   stations=[s for s in stations if s["role"] != "controller"], modules=modules,
                   headers={"stations": sh, "modules": mh})
