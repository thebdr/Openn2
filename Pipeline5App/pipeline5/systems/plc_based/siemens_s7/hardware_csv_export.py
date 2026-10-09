"""Phase 700b - the format-2 `Stations.csv` + `Modules.csv` projection of the `hardware_stations` +
`hardware_modules` SSOT tables (the OP5 BuilderData surface). A PURE projection - clean-room port of PL3's
`hardware._format2`/`write_stations`/`write_modules`.

Output matches the committed reference: **comma format-2, no BOM, CRLF**, the contract-v1 `#!openn` header
(`kind: hw/stations` / `hw/modules`, `schema: 2` = the format-2 column layout - it replaced the bare
`#!format=2` tag line on 2026-10-08) + a descriptive `# <headers>` comment (the header is a comment - OP5
reads by POSITION). The table's snake_case columns are emitted in the format-2 column order
(`_STATIONS_KEYS`/`_MODULES_KEYS`).

Place in the flow: the 700 header / 710 / 720 (run_hardware in
src://pipeline5/systems/plc_based/siemens_s7/safety/main.py) calls `project` after the build
(src://pipeline5/systems/plc_based/siemens_s7/profinet_hardware.py). Reads the `hardware_stations`
+ `hardware_modules` SSOT tables; writes BuilderData/Devices & networks/Stations.csv + Modules.csv
(`hardware_dir` of src://pipeline5/systems/plc_based/siemens_s7/output_layout.py; the header from
src://pipeline5/systems/plc_based/siemens_s7/openn_header.py) - Modules stays PL3-byte-identical below
the header because OP5 imports it; Stations carries the one sanctioned deviation (the Connector column,
below). Beside them, every run ships the DeviceTypesDatabase.csv phase 700 read (`_place_device_types_db`).
"""
from __future__ import annotations

import csv
import io
import os

from pipeline5 import config
from pipeline5.truth.database import Database
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.profinet_hardware import hardware_modules_table, hardware_stations_table

PHASE = 700

# The SSOT (snake_case) columns in format-2 ORDER + the literal descriptive-header lines (from the committed
# reference; OP5 reads by position). PL4 CONTRACT EVOLUTION (2026-07-06, co-designed with OP4): Stations gains
# a 9th `Connector` column (the head row's I/O-List col-I value, verbatim) - appended LAST so an un-updated
# positional reader is unaffected. Modules stays PL3-byte-identical. Contract v1 (2026-10-08): the `#!openn`
# header replaces the `#!format=2` tag line - `schema: 2` carries the format number.
_STATIONS_KIND = "hw/stations"
_STATIONS_KEYS = ["role", "station_name", "model_id", "ip_address", "pn_number", "subnet",
                  "custom_parameters", "group_path", "connector"]
_STATIONS_HDR = ("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet),Subnet,"
                 "Custom Parameters (separator= | ), Group = folder/subfolder/...,Connector,")

_MODULES_KIND = "hw/modules"
_MODULES_KEYS = ["station_name", "slot", "module_name", "model_id", "i_addr", "q_addr",
                 "custom_parameters", "comment"]
_MODULES_HDR = ("# Station Name,Slot (plug order),Module Name,Model Id,I Addr,Q Addr,"
                "Custom Parameters (separator= | )  syntax: [Item(i).][Ch(i).]Name=Value,Comment")
_SOURCE = {_STATIONS_KIND: "hardware_stations", _MODULES_KIND: "hardware_modules"}


def _format2(kind, header_line, rows, keys) -> str:
    """Comma format-2 text (CRLF): the `#!openn` header (the kind, schema 2, the run, the TIA folder), the
    '# <headers>' comment, then one csv-quoted row per table row (QUOTE_MINIMAL; params use '|' so they
    don't need quoting)."""
    buf = io.StringIO()
    buf.write(header.render_csv(header.fields(kind, PHASE, target=header.HARDWARE_FOLDER, source=_SOURCE[kind])))
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
    (defaults to the workspace's `Devices & networks`). A pure projection - the `findings` are the
    device-types-database placement remarks only (the facts were emitted + validated at build). Returns
    {'dir', 'stations', 'modules', 'stations_path', 'modules_path', 'device_types_db', 'device_types_source',
    'findings'} - `device_types_source` = the shipped copy's `source` citation ([[C-036]])."""
    if database is None:
        database = Database([hardware_stations_table(), hardware_modules_table()]).load(config.database_dir())
    out_dir = out_dir or LAYOUT.hardware_dir()
    stations = list(database["hardware_stations"]) if "hardware_stations" in database else []
    modules = list(database["hardware_modules"]) if "hardware_modules" in database else []
    spath = _write(out_dir, "Stations.csv", _format2(_STATIONS_KIND, _STATIONS_HDR, stations, _STATIONS_KEYS))
    mpath = _write(out_dir, "Modules.csv", _format2(_MODULES_KIND, _MODULES_HDR, modules, _MODULES_KEYS))
    dtd_path, findings = _place_device_types_db(out_dir)
    cited = header.read_header(dtd_path).get("source", "") if dtd_path else ""
    return {"dir": out_dir, "stations": len(stations), "modules": len(modules),
            "stations_path": spath, "modules_path": mpath, "device_types_db": dtd_path,
            "device_types_source": cited, "findings": findings}


_LOCAL_DTD = "DeviceTypesDatabase.csv"


_COPY_COMMENT = "the database phase 700 read - rewritten by every phase 700 run: edit the source"


def device_types_source(path: str) -> str:
    """The `source` a shipped database copy cites: the original's path relative to the monorepo's `Shared/`
    (`Shared/HardwareConfigBuilderData/DeviceTypesDatabase.csv`) or to the project folder
    (`<project folder>/config_project/...`) - never a host path (contract v1 §1.5); the file name alone for an
    original outside both."""
    original = os.path.abspath(str(path))
    roots = [("Shared", config.SHARED)]
    if config.active_project():
        project = os.path.abspath(config.active_project())
        roots.append((os.path.basename(project), project))
    for label, root in roots:
        try:
            rel = os.path.relpath(original, os.path.abspath(root))
        except ValueError:                        # another drive on Windows
            continue
        if not rel.startswith(os.pardir):
            return label + "/" + rel.replace(os.sep, "/")
    return os.path.basename(original)


def _place_device_types_db(out_dir: str) -> tuple:
    """Ship the DeviceTypesDatabase.csv phase 700 read - the project's own (`device_types_db`) or the shared one -
    BESIDE Stations.csv on every run (user 2026-10-09: "ship the deviceTypesDatabase at generation time ... cite
    the source path in the header"): the importer (Openn5App) reads that copy first, so phase 700 and the importer
    read the SAME database ([[C-028]] round 3), and the user finds it in the project's output instead of `Shared/`.
    The copy is the original byte for byte below its header, which is replaced by this generation's
    (`hw/device-types`, the run, `source` = `device_types_source`, a comment saying edits belong in the source -
    the copy is rewritten every run; whatever stood there before is overwritten). Params naming the copy itself
    leave it as it is. Returns (the placed path, findings - none)."""
    from pipeline5.config.paths import DEVICE_TYPES_DB_DEFAULT
    source = str((config.load_params() or {}).get("device_types_db") or "").strip() or DEVICE_TYPES_DB_DEFAULT
    local = os.path.join(out_dir, _LOCAL_DTD)
    if os.path.abspath(source) == os.path.abspath(local):
        return local, []
    with open(source, "rb") as original:
        text = original.read().decode("utf-8")              # a BOM stays `\ufeff` and is written back as it was
    first = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip("\ufeff").startswith("#")), "")
    delimiter = ";" if first.count(";") > first.count(",") else ","     # the loader's own sniff
    stamp = header.fields("hw/device-types", PHASE, target=header.HARDWARE_FOLDER,
                          source=device_types_source(source), comment=_COPY_COMMENT)
    os.makedirs(out_dir, exist_ok=True)
    with open(local, "w", encoding="utf-8", newline="") as copy:
        copy.write(header.stamp_csv(text, stamp, delimiter))
    return local, []
