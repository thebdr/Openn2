"""The SYCON.net handoff - the cPCI hardware configuration of an IPC-based system (the sorter PC's Hilscher
cifX PROFINET controller and its IO devices), projected from the staged I/O List for Sycon5App.

Three kinds, contract-v1 headers (Shared/PL5_OP5_contract.md §3), one folder `SyconNetProjectInterface/` beside
the TIA workspace:
  hw/sycon-device-types  SyconDeviceTypesDatabase.csv  the hand-maintained model database phase read, shipped
                         beside the tables with its `source` cited (as phase 700 ships DeviceTypesDatabase.csv):
                         Model Id (the I/O List Part No. without spaces) -> role (controller | slave | gateway |
                         ignore), the SYCON.net catalog item, whether the I/O List cards are plugged (`iolist`)
                         or the catalog defaults stay (`default`)
  hw/sycon-stations      SyconStations.csv  one row per PROFINET head of the I/O List with a mapped model:
                         Role, Station Name (the PROFINET name), Catalog Kind (master | slave | gateway),
                         Catalog Item, Model Id, IP Address, Subnet Mask, Gateway, Device Number (col F),
                         Description, Comment
  hw/sycon-modules       SyconModules.csv  one row per card of a station whose database row says `iolist`:
                         Station Name, Slot (plug order), Module Id (the card's Part No. without spaces),
                         Module Text (the SYCON.net module name when known; empty = Sycon5App resolves it by the
                         order number the catalog shows in brackets), Parameters (index=value | ...), Comment
The head rule is the staging's (`profinet_name` opens a node); the card rule is phase 700's (each distinct slot
tag under the head that is not the head's own tag is a card, the first row's Part No. its model). The second
controller of a redundant pair (same IP) is skipped with an INFO; a head without a mapped model is a WARN.
Sycon5App builds the SYCON.net project from these tables and verifies the saved project against them.
"""
from __future__ import annotations

import csv
import io
import os
import re

from pipeline5 import config
from pipeline5.findings.finding import Finding
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

PHASE = 730
FOLDER = "SyconNetProjectInterface"
DTD_FILE = "SyconDeviceTypesDatabase.csv"
STATIONS_FILE, MODULES_FILE = "SyconStations.csv", "SyconModules.csv"
KIND_DTD, KIND_STATIONS, KIND_MODULES = "hw/sycon-device-types", "hw/sycon-stations", "hw/sycon-modules"
ROLES = {"controller": "master", "slave": "slave", "gateway": "gateway", "ignore": ""}
STATIONS_KEYS = ["role", "station_name", "catalog_kind", "catalog_item", "model_id", "ip_address", "subnet_mask",
                 "gateway", "device_number", "description", "comment"]
STATIONS_HDR = ("# Role,Station Name,Catalog Kind,Catalog Item,Model Id,IP Address,Subnet Mask,Gateway,"
                "Device Number,Description,Comment")
MODULES_KEYS = ["station_name", "slot", "module_id", "module_text", "parameters", "comment"]
MODULES_HDR = "# Station Name,Slot (plug order),Module Id,Module Text,Parameters (index=value | ...),Comment"
DEFAULT_MASK = "255.255.255.0"
SYCON_DTD_DEFAULT = os.path.join(config.SHARED, "HardwareConfigBuilderData", DTD_FILE)


def _f(type_, severity, detail, location=""):
    return Finding(phase=PHASE, type=type_, severity=severity, detail=detail, location=location)


def model_id(part_no) -> str:
    return str(part_no or "").replace(" ", "").strip()


FIVES_CODE = re.compile(r"^\d{2}C_\d{5}$")           # a Fives catalog code (`14C_00051`), never a model


def card_model(row) -> str:
    """A card row's model: its Part No., unless that is a Fives code - some I/O Lists shift the card rows one
    column left (the order number in `Manufacturer`, the Fives code in `Part No.`)."""
    for key in ("part_no", "manufacturer"):
        value = model_id(row.get(key))
        if value and not FIVES_CODE.match(value):
            return value
    return ""


# --- the database -------------------------------------------------------------------------------- #
def load_dtd(path: str | None = None) -> dict:
    """{MODEL ID upper: {role, catalog_item, modules, gsdml, comment}} from the hand-maintained csv (comment and
    header lines skipped; ',' or ';' delimited)."""
    path = path or SYCON_DTD_DEFAULT
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    delimiter = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","
    out = {}
    for row in csv.reader(lines, delimiter=delimiter):
        row = [c.strip() for c in row] + [""] * 6
        if not row[0]:
            continue
        role = row[1].lower()
        if role not in ROLES:
            raise ValueError("SyconDeviceTypesDatabase: unknown role %r for %r" % (row[1], row[0]))
        out[model_id(row[0]).upper()] = {"model_id": model_id(row[0]), "role": role, "catalog_item": row[2],
                                         "modules": (row[3].lower() or "default"), "gsdml": row[4], "comment": row[5]}
    return out


# --- the build ------------------------------------------------------------------------------------ #
def build(rows, dtd: dict) -> tuple:
    """(stations, modules, findings) from staged I/O List rows (dicts with the canonical columns), in order."""
    stations, modules, findings = [], [], []
    cur = None
    controller = None

    def finalize():
        if cur is None:
            return
        rec = cur["rec"]
        if rec["modules"] != "iolist":
            return
        cards, order = {}, []
        for s in cur["signals"]:
            slot = str(s.get("slot") or "").strip()
            if not slot or slot == cur["head_tag"]:
                continue
            if slot not in cards:
                cards[slot] = []
                order.append(slot)
            cards[slot].append(s)
        for n, slot in enumerate(order, start=1):
            model = next((m for s in cards[slot] if (m := card_model(s))), "")
            if not model:
                findings.append(_f("sycon_card_without_model", "WARN", "station %r: slot tag %r has no Part No. - no module row"
                                   % (cur["name"], slot), cur["where"]))
                continue
            modules.append({"station_name": cur["name"], "slot": str(n), "module_id": model, "module_text": "",
                            "parameters": "", "comment": slot})

    for row in rows:
        name = str(row.get("profinet_name") or "").strip()
        if not name:
            if cur is not None:
                cur["signals"].append(row)
            continue
        finalize()
        cur = None
        where = str(row.get("source_cell") or row.get("location") or "")
        model = model_id(row.get("part_no"))
        ip = str(row.get("profinet_ip") or "").strip()
        if not model:
            findings.append(_f("sycon_head_without_model", "WARN", "station %r has no Part No. - skipped" % name, where))
            continue
        rec = dtd.get(model.upper())
        if rec is None:
            findings.append(_f("sycon_model_not_in_dtd", "WARN", "station %r: model %r is not in the SYCON device-types "
                               "database - skipped" % (name, model), where))
            continue
        if rec["role"] == "ignore":
            findings.append(_f("sycon_model_ignored", "INFO", "station %r (%s): %s" % (name, model, rec["comment"]), where))
            continue
        if rec["role"] == "controller":
            if controller is not None:
                findings.append(_f("sycon_second_controller", "INFO", "station %r (%s, %s) skipped: the controller is %r"
                                   % (name, model, ip, controller), where))
                continue
            controller = name
        stations.append({"role": rec["role"], "station_name": name, "catalog_kind": ROLES[rec["role"]],
                         "catalog_item": rec["catalog_item"], "model_id": model, "ip_address": ip,
                         "subnet_mask": DEFAULT_MASK, "gateway": "",
                         "device_number": str(row.get("id_node") or "").strip(),
                         "description": " ".join(str(row.get("description_module") or "").split()),
                         "comment": " ".join(str(row.get("manufacturer") or "").split())})
        cur = {"name": name, "rec": rec, "head_tag": str(row.get("slot") or "").strip(), "signals": [], "where": where}
    finalize()
    if controller is None:
        findings.append(_f("sycon_no_controller", "FAIL", "no controller head in the I/O List (a model with role "
                           "`controller` in the SYCON device-types database)"))
    return stations, modules, findings


# --- the projection -------------------------------------------------------------------------------- #
def _csv(kind, header_line, rows, keys, source) -> str:
    buf = io.StringIO()
    buf.write(header.render_csv(header.fields(kind, PHASE, target=FOLDER, source=source)))
    buf.write(header_line + "\r\n")
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows:
        w.writerow([str(r.get(k, "")) for k in keys])
    return buf.getvalue()


def _write(out_dir, filename, text) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def _ship_dtd(out_dir, source_path) -> str:
    """The database copy beside the tables, its header replaced by this generation's (the `source` cited)."""
    from pipeline5.systems.plc_based.siemens_s7.hardware_csv_export import device_types_source
    with open(source_path, "rb") as f:
        text = f.read().decode("utf-8")
    body = header.strip_header(text) if hasattr(header, "strip_header") else _strip(text)
    stamp = header.fields(KIND_DTD, PHASE, target=FOLDER, source=device_types_source(source_path),
                          comment="the database the SYCON handoff read - rewritten by every run: edit the source")
    return _write(out_dir, DTD_FILE, header.render_csv(stamp) + body)


def _strip(text: str) -> str:
    lines = text.lstrip("﻿").splitlines()
    if lines and lines[0].strip().rstrip(",;") == header.OPEN:
        end = next((i for i, ln in enumerate(lines) if ln.strip().rstrip(",;") == header.END), -1)
        lines = lines[end + 1:]
    return "\r\n".join(lines) + "\r\n"


def project(rows, out_dir: str, dtd_path: str | None = None, source_label: str = "signals") -> dict:
    """Build from staged rows and write the three files into `out_dir`. Returns the counts, paths and findings."""
    dtd_path = dtd_path or SYCON_DTD_DEFAULT
    dtd = load_dtd(dtd_path)
    stations, modules, findings = build(rows, dtd)
    spath = _write(out_dir, STATIONS_FILE, _csv(KIND_STATIONS, STATIONS_HDR, stations, STATIONS_KEYS, source_label))
    mpath = _write(out_dir, MODULES_FILE, _csv(KIND_MODULES, MODULES_HDR, modules, MODULES_KEYS, source_label))
    dpath = _ship_dtd(out_dir, dtd_path)
    return {"dir": out_dir, "stations": len(stations), "modules": len(modules), "stations_path": spath,
            "modules_path": mpath, "device_types_db": dpath, "findings": findings,
            "controller": next((s["station_name"] for s in stations if s["role"] == "controller"), "")}


def stage_rows(iolist_path: str) -> tuple:
    """Stage an I/O List with the active configuration (the builtin params with the path swapped in) and return
    (its signal rows in document order, the staging findings)."""
    from pipeline5.phases.staging import iolist as staging
    params = dict(config.load_params() or {})
    params["iolist_path"] = iolist_path
    database, findings = staging.stage_iolist(params, save=False)
    rows = list(database["signals"]) if "signals" in database else []
    return rows, findings


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="write the SYCON.net handoff of an I/O List")
    p.add_argument("--iolist", required=True)
    p.add_argument("--out", required=True, help="the SyconNetProjectInterface folder to write")
    p.add_argument("--dtd", default="", help="the SYCON device-types database (default: Shared/HardwareConfigBuilderData)")
    a = p.parse_args(argv)
    rows, findings = stage_rows(a.iolist)
    res = project(rows, a.out, a.dtd or None, source_label=os.path.basename(a.iolist))
    for f in findings + res["findings"]:
        print("[%s] %s - %s  @ %s" % (f.severity, f.type, f.detail, f.location))
    print("SYCON handoff: %d stations (controller %r) + %d module rows -> %s" % (res["stations"], res["controller"], res["modules"], res["dir"]))
    return 1 if any(f.severity == "FAIL" for f in res["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
