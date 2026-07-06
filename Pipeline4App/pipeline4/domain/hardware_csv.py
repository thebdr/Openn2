"""Phase 700b - the format-2 `Stations.csv` + `Modules.csv` projection of the `hardware_stations` +
`hardware_modules` SSOT tables (the OP4 BuilderData surface). A PURE projection - clean-room port of PL3's
`hardware._format2`/`write_stations`/`write_modules`.

Output matches the committed reference: **comma format-2, no BOM, CRLF**, a `#!format=2` tag line + a
descriptive `# <headers>` comment (the header is a comment - OP4 reads by POSITION). The table's snake_case
columns are emitted in the format-2 column order (`_STATIONS_KEYS`/`_MODULES_KEYS`).
"""
from __future__ import annotations

import csv
import io
import os

from pipeline4.core import config
from pipeline4.core.database import Database
from pipeline4.domain.hardware import hardware_modules_table, hardware_stations_table

# The SSOT (snake_case) columns in format-2 ORDER, and the literal format-2 tag + descriptive-header lines
# (from the committed reference; OP4 reads by position). PL4 CONTRACT EVOLUTION (2026-07-06, co-designed
# with OP4): Stations gains a 9th `Connector` column (the head row's I/O-List col-I value, verbatim) -
# appended LAST so an un-updated positional reader is unaffected. Modules stays PL3-byte-identical.
_STATIONS_KEYS = ["role", "station_name", "model_id", "ip_address", "pn_number", "subnet",
                  "custom_parameters", "group_path", "connector"]
_STATIONS_FMT2 = "#!format=2,,,,,,,,,"
_STATIONS_HDR = ("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet),Subnet,"
                 "Custom Parameters (separator= | ), Group = folder/subfolder/...,Connector,")

_MODULES_KEYS = ["station_name", "slot", "module_name", "model_id", "i_addr", "q_addr",
                 "custom_parameters", "comment"]
_MODULES_FMT2 = "#!format=2,,,,,,,"
_MODULES_HDR = ("# Station Name,Slot (plug order),Module Name,Model Id,I Addr,Q Addr,"
                "Custom Parameters (separator= | )  syntax: [Item(i).][Ch(i).]Name=Value,Comment")


def _format2(fmt2_line, header_line, rows, keys) -> str:
    """Comma format-2 text (CRLF): the '#!format=2' tag, the '# <headers>' comment, then one csv-quoted row
    per table row (QUOTE_MINIMAL; params use '|' so they don't need quoting)."""
    buf = io.StringIO()
    buf.write(fmt2_line + "\r\n")
    buf.write(header_line + "\r\n")
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows:
        w.writerow([str(r.get(k, "")) for k in keys])
    return buf.getvalue()


def _write(out_dir, filename, text) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:    # no BOM, CRLF (matches the reference)
        f.write(text)
    return path


def project(database: Database | None = None, out_dir: str | None = None) -> dict:
    """Write Stations.csv (from `hardware_stations`) + Modules.csv (from `hardware_modules`) to `out_dir`
    (defaults to `config.hardware_dir()`). A pure projection - `findings` is empty (the facts were emitted
    + validated at build). Returns {'dir', 'stations', 'modules', 'stations_path', 'modules_path', 'findings'}."""
    if database is None:
        database = Database([hardware_stations_table(), hardware_modules_table()]).load(config.database_dir())
    out_dir = out_dir or config.hardware_dir()
    stations = list(database["hardware_stations"]) if "hardware_stations" in database else []
    modules = list(database["hardware_modules"]) if "hardware_modules" in database else []
    spath = _write(out_dir, "Stations.csv", _format2(_STATIONS_FMT2, _STATIONS_HDR, stations, _STATIONS_KEYS))
    mpath = _write(out_dir, "Modules.csv", _format2(_MODULES_FMT2, _MODULES_HDR, modules, _MODULES_KEYS))
    return {"dir": out_dir, "stations": len(stations), "modules": len(modules),
            "stations_path": spath, "modules_path": mpath, "findings": []}
