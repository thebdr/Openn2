"""The SYCON.net handoff folder PL5 writes (`SyconNetProjectInterface/`): three csv files with a contract-v1
`#!openn` header - hw/sycon-stations (SyconStations.csv), hw/sycon-modules (SyconModules.csv),
hw/sycon-device-types (SyconDeviceTypesDatabase.csv). Read by position (the `#` header line documents the
columns), like OP5 reads the TIA kinds.
"""
import csv
import os
from dataclasses import dataclass, field

STATIONS_FILE, MODULES_FILE, DTD_FILE = "SyconStations.csv", "SyconModules.csv", "SyconDeviceTypesDatabase.csv"
STATION_KEYS = ["role", "station_name", "catalog_kind", "catalog_item", "model_id", "ip_address", "subnet_mask",
                "gateway", "device_number", "description", "comment"]
MODULE_KEYS = ["station_name", "slot", "module_id", "module_text", "parameters", "comment"]


class HandoffError(ValueError):
    pass


def read_headed_csv(path):
    """(header dict, data rows) of a `#!openn` csv: the directives between `#!openn` and `#!end`, the `#` comment
    lines dropped, Excel's trailing delimiters tolerated."""
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
        if not ln.strip() or ln.lstrip().startswith("#"):
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
        return self.modules.get(station, [])


def load_handoff(folder):
    spath, mpath = os.path.join(folder, STATIONS_FILE), os.path.join(folder, MODULES_FILE)
    if not os.path.exists(spath):
        raise HandoffError("no %s in %s" % (STATIONS_FILE, folder))
    sh, srows = read_headed_csv(spath)
    if sh.get("kind") != "hw/sycon-stations":
        raise HandoffError("%s is not hw/sycon-stations (kind %r)" % (spath, sh.get("kind")))
    stations = [dict(zip(STATION_KEYS, r + [""] * len(STATION_KEYS))) for r in srows if r and r[0]]
    controllers = [s for s in stations if s["role"] == "controller"]
    if len(controllers) != 1:
        raise HandoffError("%d controller rows in %s (one expected)" % (len(controllers), spath))
    modules, mh = {}, {}
    if os.path.exists(mpath):
        mh, mrows = read_headed_csv(mpath)
        if mh.get("kind") != "hw/sycon-modules":
            raise HandoffError("%s is not hw/sycon-modules (kind %r)" % (mpath, mh.get("kind")))
        for r in mrows:
            if not r or not r[0]:
                continue
            m = dict(zip(MODULE_KEYS, r + [""] * len(MODULE_KEYS)))
            modules.setdefault(m["station_name"], []).append(m)
    return Handoff(folder=folder, controller=controllers[0],
                   stations=[s for s in stations if s["role"] != "controller"], modules=modules,
                   headers={"stations": sh, "modules": mh})
