"""The SYCON.net handoff - the cPCI hardware configuration of an IPC-based system (the sorter PC's Hilscher
cifX PROFINET controller and its IO devices), projected from the staged I/O List for Sycon5App.

Three kinds, contract-v1 headers (Shared/PL5_OP5_contract.md §3), one folder `SyconNetProjectInterface/` beside
the TIA workspace:
  hw/sycon-device-types  SyconDeviceTypesDatabase.csv  the hand-maintained model database phase read, shipped
                         beside the tables with its `source` cited (as phase 700 ships DeviceTypesDatabase.csv):
                         Model Id (the I/O List Part No. without spaces) -> role (controller | slave | gateway |
                         ignore), the SYCON.net catalog item, whether the I/O List cards are plugged (`iolist`),
                         the catalog defaults stay (`default`) or the IO-Link ports are configured from the
                         I/O List's connector rows (`iolink-ports`, the AL1202 rule below)
  hw/sycon-stations      SyconStations.csv  one row per PROFINET head of the I/O List with a mapped model:
                         Role, Station Name (the PROFINET name), Catalog Kind (master | slave | gateway),
                         Catalog Item, Model Id, GSDML (the file of the catalog entry to take: the catalog lists
                         one same-named entry per GSDML version of a device), IP Address, Subnet Mask, Gateway,
                         Update Time (ms; the controller's Stations Timing: 8, or 2 for a station whose signals
                         mention a control zone, check position, load accuracy or synchronism), Device Number
                         (col F), Description, Comment
  hw/sycon-modules       SyconModules.csv  one row per card of a station whose database row says `iolist`, one
                         per port of a station whose row says `iolink-ports`: Station Name, Slot (plug order),
                         Subslot (empty = a module row; a submodule row's subslot), Module Id (the card's Part No.
                         without spaces; empty for a port), Module Text (the SYCON.net module name when known;
                         empty = Sycon5App resolves it by the order number the catalog shows in brackets; the port
                         submodule text for a port), Parameters (name=value | ...: a parameter index within the
                         module's first record, `potential_group` = the module's last parameter row - set on
                         an ET200SP's first module and first output module -, `record:<index>=<hex bytes>` = the
                         saved record must read these bytes, verification only), Comment. A row with Slot 0 is
                         a submodule of the device itself (a SCALANCE switch's PN-IO, policy `scalance-pnio`):
                         never plugged, its parameters set and its records checked
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
# the production folder of the sorter PC (user 2026-10-24, the FVZ reference `PRODUCTION/`): one folder per cifX card,
# `HilscherIOCard<n>/`, holding that card's SYCON.net project `HilscherPnCard_<n>.spj` (Sycon5App builds it beside
# this handoff's `SyconNetProjectInterface/`), and `IODriver/BusField.csv` for every card
PRODUCTION_FOLDER, CARD_FOLDER, PROJECT_NAME = "PRODUCTION", "HilscherIOCard%d", "HilscherPnCard_%d"
KIND_DTD, KIND_STATIONS, KIND_MODULES = "hw/sycon-device-types", "hw/sycon-stations", "hw/sycon-modules"
ROLES = {"controller": "master", "slave": "slave", "gateway": "gateway", "ignore": ""}
STATIONS_KEYS = ["role", "station_name", "catalog_kind", "catalog_item", "model_id", "gsdml", "ip_address",
                 "subnet_mask", "gateway", "update_time_ms", "device_number", "description", "comment",
                 "symbolic_name", "fld"]
STATIONS_HDR = ("# Role,Station Name,Catalog Kind,Catalog Item,Model Id,GSDML (the file of the catalog entry to take),"
                "IP Address,Subnet Mask,Gateway,Update Time (ms - the controller's Stations Timing; empty for the "
                "controller),Device Number,Description,Comment,Symbolic Name (the netDevice label nnn[_Custom Description] - "
                "the node number = the IP's last octet + the device-types rule's text; empty for the controller),FLD (the I/O "
                "List's full tag)")
SYMBOLIC_RULES = ("default", "fld", "variable", "description")
DEFAULT_UPDATE_TIME_MS = 8            # user 2026-10-23: "station timing 8ms for all nodes"
# ... except the nodes that acquire fast signals (user 2026-10-23: "control zones, check position photocells of
# sorter; load accuracy, check position, synchronism on induction lines -> Station Timing = 2ms"; then the
# recentering sensors: "DISTANCE SENSOR / LEFT SIDE RECENTERING 2, PHOTOCELL / BETWEEN CELLS RECENTERING 2 ->
# 2ms"): a station whose signal descriptions mention one of these takes FAST_UPDATE_TIME_MS
FAST_UPDATE_TIME_MS = 2
FAST_SIGNAL_KEYWORDS = ("control zone", "check position", "load accuracy", "synchronism", "recentering")
MODULES_KEYS = ["station_name", "slot", "subslot", "module_id", "module_text", "parameters", "comment"]
MODULES_HDR = ("# Station Name,Slot (plug order),Subslot (empty = a module row; a submodule's subslot),Module Id,"
               "Module Text,Parameters (name=value | ...: a parameter index in the first record or potential_group = the "
               "last parameter row),Comment")
MODULE_POLICIES = ("default", "iolist", "iolink-ports", "scalance-pnio", "fixed")
# SCALANCE XC200 switches (policy `scalance-pnio`, user 2026-10-23 "let's also add the scalance switches, with the
# following parameters"): the DAP's PN-IO interface submodule (slot 0, subslot 32768) takes Loop Detection
# `Interface Mode` = Off and Port Mirroring `Mirroring Mode` = Off (the GSDML defaults are 'Local configuration');
# Media redundancy `Not by STEP7` Off, Monitor Barrier Off, Monitor Port 1 are the defaults. The parameter grid
# rows: 1 Not by STEP7, 3 Interface Mode, 5 Mirroring Mode, 6 Monitor Barrier, 7 Monitor Port (index = row - 1);
# the saved records (GSDML-V2.42-Siemens-002A-SCALANCE_XC200: index 3 / 12309 / 12312) must read these bytes.
SCALANCE_PNIO_PARAMS = ("2=Off | 4=Off"
                        " | record:3=00 03 00 06 01 00 00 00 00 00"
                        " | record:12309=30 19 00 08 01 01 00 01 01 00 00 02"
                        " | record:12312=30 1C 00 08 01 01 00 00 00 01 00 00")
# The XC216-4C's four combo ports (1-4, subslots 32769-32772) and the XC206-2 SFP's two fibre ports (7-8) are
# pluggable port submodules; the project's SFP is the SFP991-1 everywhere (the cabinet drawings' parts lists:
# 6GK5991-1AD00-8GA0 / -8AA0) and every such port takes it (user 2026-10-23: "Configure all four combo ports of
# every XC216-4C as SFP 991-1 A" - the GSDML's submodule text). The XC208's eight ports are fixed.
SCALANCE_COMBO_PORTS = {"6GK5216-4BS00-2AC2": ((1, 2, 3, 4), "SFP 991-1 A", "6GK5991-1AD00-8GA0"),
                        "6GK5206-2BS00-2AC2": ((7, 8), "SFP 991-1 A", "6GK5991-1AD00-8AA0")}
# ET200SP (policy `iolist`): the first module and the first output module open a new potential group (a light
# BaseUnit) - the module's last parameter row in SYCON.net, `Potential group` (user 2026-10-23). A card is an
# output module by its signals' addresses (`Q.` and no `I.`), else by its order-number family (DQ 6ES7132, AQ 6ES7135).
POTENTIAL_GROUP_PARAM = "potential_group"
POTENTIAL_GROUP_NEW = "Enable new potential group (light BaseUnit)"
OUTPUT_FAMILIES = ("6ES7132", "6ES7135")
DEFAULT_MASK = "255.255.255.0"
SYCON_DTD_DEFAULT = os.path.join(config.SHARED, "HardwareConfigBuilderData", DTD_FILE)

# --- the IO-Link ports of an AL1202 (policy `iolink-ports`) ------------------------------------------ #
# The rules of the Fives tool TAG_IFM_PROFINET_AL1202_R0.17.xlsm (sheet Tab + the DATA INSER macro): a port's
# SYCON.net submodule is fixed by its device's footprint - the input bytes (the PQI byte included) and the
# output bytes; "not used" is `Disabled`; a port whose pin 4 is unused and whose pin 2 carries a digital input
# is a `Digital Input + PQI` all the same. Read back from the I/O List: the rows of a port are the rows with its
# connector (`X01`..`X08`) plus the connector-less rows that follow (a stack light's lamps), its footprint the
# span of their `I.<node>.<byte>.<bit>` / `Q...` addresses (a 32-byte IO-Link device lists its output start only:
# the input span tells the family, any output row the In/Out variant), a digital output the Q address on the
# pin-4 row itself. The `8 Ports` module sits in slot 1 by default with the `IO-Link Master` in sub 1; the ports
# follow it (port n = sub n + PORT_SUBSLOT_BASE - to be verified on the VM).
PORT_COUNT = 8
PORT_SUBSLOT_BASE = 1
PORT_SUBMODULES = {
    (0, 0): "Disabled",
    (1, 0): "Digital Input + PQI",
    (1, 1): "Digital Output + PQI",
    (1, 2): "IO-Link Out  2 Byte + PQI",
    (1, 16): "IO-Link Out 16 Byte + PQI",
    (3, 0): "IO-Link In 2 Byte + PQI",
    (3, 2): "IO-Link In/Out  2/ 2 Byte + PQI",
    (33, 0): "IO-Link In 32 Byte + PQI",
    (33, 32): "IO-Link In/Out 32/32 Byte + PQI",
}
PORT_RE = re.compile(r"^X(\d{1,2})$", re.I)
BIT_RE = re.compile(r"^([IQ])\.(\d+)\.(\d+)\.(\d+)$", re.I)


def signal_text(row) -> str:
    return " ".join(str(row.get(k) or "") for k in ("desc_l1", "desc_l1b", "desc_l2", "desc_l2b", "mnemonic")).lower()


def station_is_fast(signals) -> bool:
    """Whether a station acquires fast signals (a keyword of FAST_SIGNAL_KEYWORDS in a signal's descriptions)."""
    return any(k in signal_text(s) for s in signals for k in FAST_SIGNAL_KEYWORDS)


def card_is_output(rows, model) -> bool:
    bits = [str(r.get("bit") or "").strip().upper() for r in rows]
    has_i, has_q = any(b.startswith("I.") for b in bits), any(b.startswith("Q.") for b in bits)
    if has_i or has_q:
        return has_q and not has_i
    return model_id(model).upper().startswith(OUTPUT_FAMILIES)


def port_rows(signals) -> dict:
    """{'X01': [rows], ...}: a row with a connector opens (or continues) its port; a row without one belongs to
    the port opened last."""
    ports, cur = {}, None
    for s in signals:
        m = PORT_RE.match(str(s.get("connector") or "").strip())
        if m:
            cur = "X%02d" % int(m.group(1))
            ports.setdefault(cur, [])
        if cur is not None:
            ports[cur].append(s)
    return ports


def port_footprint(rows) -> tuple:
    """(input bytes, output bytes, digital output) of a port from its rows' addresses."""
    ins, outs, do = set(), set(), False
    for s in rows:
        m = BIT_RE.match(str(s.get("bit") or "").strip())
        if not m:
            continue
        byte = int(m.group(3))
        if m.group(1).upper() == "I":
            ins.add(byte)
        else:
            outs.add(byte)
            if str(s.get("pin_no") or "").strip() == "4":
                do = True
    size_in = (max(ins) - min(ins) + 1) if ins else 0
    size_out = (max(outs) - min(outs) + 1) if outs else 0
    return size_in, size_out, do


def port_submodule(size_in, size_out, do) -> str:
    """The SYCON.net port submodule of a footprint, '' when none of the table fits."""
    if do and size_in <= 1 and size_out == 1:
        return PORT_SUBMODULES[(1, 1)]
    if size_in == 33:
        return PORT_SUBMODULES[(33, 32 if size_out else 0)]
    if size_in == 3:
        return PORT_SUBMODULES[(3, 2 if size_out else 0)]
    if size_in == 1 and size_out == 0:
        return PORT_SUBMODULES[(1, 0)]
    if size_in <= 1 and size_out:
        return PORT_SUBMODULES[(1, 2 if size_out <= 2 else 16)]
    if size_in == 0 and size_out == 0:
        return PORT_SUBMODULES[(0, 0)]
    return ""


def network_of(ip: str, mask: str = DEFAULT_MASK):
    """The network address of `ip` under `mask`, as a tuple of four ints; None for a malformed address."""
    try:
        a, m = [int(x) for x in str(ip).split(".")], [int(x) for x in str(mask).split(".")]
    except ValueError:
        return None
    if len(a) != 4 or len(m) != 4:
        return None
    return tuple(x & y for x, y in zip(a, m))


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
    """{MODEL ID upper: {role, catalog_item, modules, gsdml, comment, symbolic, fixed_modules}} from the
    hand-maintained csv (comment and header lines skipped; ',' or ';' delimited). Columns 7 and 8 (2026-10-24):
    the symbolic-name rule and the module texts of the `fixed` policy; column 9 (2026-10-25): the DAP parameters
    (slot 0 subslot 1: `index=value | record:<idx>=<bytes>`)."""
    path = path or SYCON_DTD_DEFAULT
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    delimiter = ";" if lines and lines[0].count(";") > lines[0].count(",") else ","
    out = {}
    for row in csv.reader(lines, delimiter=delimiter):
        row = [c.strip() for c in row] + [""] * 9
        if not row[0]:
            continue
        role = row[1].lower()
        if role not in ROLES:
            raise ValueError("SyconDeviceTypesDatabase: unknown role %r for %r" % (row[1], row[0]))
        policy = row[3].lower() or "default"
        if policy not in MODULE_POLICIES:
            raise ValueError("SyconDeviceTypesDatabase: unknown modules policy %r for %r" % (row[3], row[0]))
        symbolic = row[6].lower() or "default"
        if symbolic not in SYMBOLIC_RULES:
            raise ValueError("SyconDeviceTypesDatabase: unknown symbolic-name rule %r for %r" % (row[6], row[0]))
        fixed = fixed_modules(row[7])
        if policy == "fixed" and not fixed:
            raise ValueError("SyconDeviceTypesDatabase: policy fixed without Fixed Modules for %r" % row[0])
        out[model_id(row[0]).upper()] = {"model_id": model_id(row[0]), "role": role, "catalog_item": row[2],
                                         "modules": policy, "gsdml": row[4], "comment": row[5],
                                         "symbolic": symbolic, "fixed_modules": fixed, "dap_parameters": row[8]}
    return out


CONNECTOR_LIST = re.compile(r"^\s*(X\d+)\s*:\s*(.*)$", re.I)


def fixed_modules(text):
    """The Fixed Modules column: module texts `|` separated, in slot order - or, `;` separated, one such list per
    connector (`X2: *OUT 128 Byte | *IN 128 Byte; X1: *IN 128 Byte | *OUT 128 Byte` - user 2026-10-24: a PN/PN
    coupler's X1 side has the module positions of the X2 side mirrored; the I/O List names the side in its
    Connector column). A list, or {CONNECTOR: list}."""
    pieces = [piece for piece in str(text or "").split(";") if piece.strip()]
    if pieces and all(CONNECTOR_LIST.match(piece) for piece in pieces):
        out = {}
        for piece in pieces:
            m = CONNECTOR_LIST.match(piece)
            out[m.group(1).upper()] = [t.strip() for t in m.group(2).split("|") if t.strip()]
        return out
    return [t.strip() for t in str(text or "").split("|") if t.strip()]


# --- the build ------------------------------------------------------------------------------------ #
def head_model(row, dtd) -> tuple:
    """(model id, keyed by the manufacturer?) of a head row: its Part No.; without one, its Manufacturer when the
    database carries that as a model (the Vitronic camera heads of the FVT lists, 2026-10-24)."""
    model = model_id(row.get("part_no"))
    if model:
        return model, False
    alt = model_id(row.get("manufacturer"))
    if alt and alt.upper() in dtd:
        return alt, True
    return "", False


def cards_of(rows, dtd: dict) -> list:
    """The cifX cards of the list, one per PROFINET network in document order: [{card, name, ip, net, sheet}]. A
    second controller head on a network already listed is the redundant card, not a card of its own."""
    cards = []
    for row in rows:
        name = str(row.get("profinet_name") or "").strip()
        if not name:
            continue
        model, _by = head_model(row, dtd)
        rec = dtd.get(model.upper()) if model else None
        if rec is None or rec["role"] != "controller":
            continue
        ip = str(row.get("profinet_ip") or "").strip()
        net = network_of(ip)
        if any(c["net"] == net for c in cards):
            continue
        cards.append({"card": len(cards) + 1, "name": name, "ip": ip, "net": net,
                      "sheet": str(row.get("source_sheet") or "").strip()})
    return cards


def symbolic_text(rule, row) -> str:
    """The description part of a station's netDevice label by the database's rule (user 2026-10-24, the edited
    sorter project); empty for `default`."""
    if rule == "fld":                 # the functional unit + the location's FIRST segment (=TRIB-MA01 of -MA01-AEC1)
        head = str(row.get("location") or "").strip().strip("-").split("-")[0]
        return str(row.get("functional_unit") or "").strip() + ("-" + head if head else "")
    if rule == "variable":
        return " ".join(str(row.get("desc_l1b") or "").split())
    if rule == "description":
        return " ".join(str(row.get("description_module") or "").split())
    return ""


def symbolic_name(rule, row, ip="") -> str:
    """The netDevice label of a slave station: `nnn[_Custom Description]` - nnn the node number (the IP's last
    octet, three digits) and, when the rule gives one, `_` + its text (user 2026-10-25: `088_=TRIB-CA01`, `087`).
    Without an IP the text alone."""
    text = symbolic_text(rule, row)
    parts = str(ip or "").strip().split(".")
    node = parts[-1] if len(parts) == 4 and parts[-1].isdigit() else ""
    if not node:
        return text
    return "%03d" % int(node) + ("_" + text if text else "")


def build(rows, dtd: dict, update_time_ms=DEFAULT_UPDATE_TIME_MS, card: int = 1) -> tuple:
    """(stations, modules, findings) from staged I/O List rows (dicts with the canonical columns), in order, for
    the cifX card `card` (1-based, `cards_of`): its controller and the stations on its PROFINET network; every
    station gets `update_time_ms` as its PROFINET updating time."""
    stations, modules, findings = [], [], []
    cur = None
    controller, controller_net = None, None
    seen_names, seen_ips = {}, {}
    cards = cards_of(rows, dtd)
    chosen = cards[card - 1] if 0 < card <= len(cards) else None
    if cards and chosen is None:
        findings.append(_f("sycon_no_card", "FAIL", "the I/O List has %d cifX card(s) - no card %d" % (len(cards), card)))
        return stations, modules, findings

    def finalize():
        if cur is None:
            return
        rec = cur["rec"]
        if cur["station"]["update_time_ms"] and station_is_fast(cur["signals"]):
            cur["station"]["update_time_ms"] = str(FAST_UPDATE_TIME_MS)
            cur["station"]["comment"] = (cur["station"]["comment"] + " | fast: " + ", ".join(
                sorted({k for s in cur["signals"] for k in FAST_SIGNAL_KEYWORDS if k in signal_text(s)}))).strip(" |")
        if rec.get("dap_parameters"):                      # the device's own submodule (slot 0, subslot 1)
            modules.append({"station_name": cur["name"], "slot": "0", "subslot": "1", "module_id": "",
                            "module_text": "", "parameters": rec["dap_parameters"],
                            "comment": "DAP parameters of %s" % rec["model_id"]})
        if rec["modules"] == "fixed":                      # the database's module texts, in slot order
            fixed = rec.get("fixed_modules") or []
            if isinstance(fixed, dict):                    # per connector: the head row's Connector column picks
                connector = str(cur["row"].get("connector") or "").strip().upper()
                if connector not in fixed:
                    findings.append(_f("sycon_connector_unknown", "WARN", "station %r: connector %r has no fixed modules "
                                       "(%s) - none plugged" % (cur["name"], connector, " / ".join(sorted(fixed))), cur["where"]))
                    return
                fixed = fixed[connector]
            for n, text in enumerate(fixed, start=1):
                modules.append({"station_name": cur["name"], "slot": str(n), "subslot": "", "module_id": "",
                                "module_text": text, "parameters": "", "comment": "fixed module of %s" % rec["model_id"]})
            return
        if rec["modules"] == "scalance-pnio":
            modules.append({"station_name": cur["name"], "slot": "0", "subslot": "32768", "module_id": "",
                            "module_text": "PN-IO", "parameters": SCALANCE_PNIO_PARAMS,
                            "comment": "PN-IO: Loop Detection Interface Mode Off, Port Mirroring Mode Off"})
            port_numbers, text, sfp = SCALANCE_COMBO_PORTS.get(rec["model_id"].upper(), ((), "", ""))
            for n in port_numbers:
                modules.append({"station_name": cur["name"], "slot": "0", "subslot": str(0x8000 + n), "module_id": sfp,
                                "module_text": text, "parameters": "", "comment": "port %d: SFP991-1" % n})
            return
        if rec["modules"] == "iolink-ports":
            ports = port_rows(cur["signals"])
            for n in range(1, PORT_COUNT + 1):
                port = "X%02d" % n
                prow = ports.get(port, [])
                size_in, size_out, do = port_footprint(prow)
                text = port_submodule(size_in, size_out, do)
                devices = sorted({str(r.get("device") or r.get("location") or "").strip() for r in prow
                                  if str(r.get("device") or r.get("location") or "").strip()})
                if not text:
                    findings.append(_f("sycon_port_footprint_unknown", "WARN", "station %r port %s: %d input, %d output "
                                       "bytes%s fit no port submodule - no row" % (cur["name"], port, size_in, size_out,
                                                                                   " (digital output)" if do else ""), cur["where"]))
                    continue
                modules.append({"station_name": cur["name"], "slot": "1", "subslot": str(PORT_SUBSLOT_BASE + n),
                                "module_id": "", "module_text": text, "parameters": "",
                                "comment": "%s [%d in, %d out] %s" % (port, size_in, size_out, " ".join(devices))})
            return
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
        first_done, first_output_done = False, False
        for n, slot in enumerate(order, start=1):
            model = next((m for s in cards[slot] if (m := card_model(s))), "")
            if not model:
                findings.append(_f("sycon_card_without_model", "WARN", "station %r: slot tag %r has no Part No. - no module row"
                                   % (cur["name"], slot), cur["where"]))
                continue
            output = card_is_output(cards[slot], model)
            params = []
            if not first_done or (output and not first_output_done):
                params.append("%s=%s" % (POTENTIAL_GROUP_PARAM, POTENTIAL_GROUP_NEW))
            first_done = True
            first_output_done = first_output_done or output
            modules.append({"station_name": cur["name"], "slot": str(n), "subslot": "", "module_id": model,
                            "module_text": "", "parameters": " | ".join(params), "comment": slot})

    for row in rows:
        name = str(row.get("profinet_name") or "").strip()
        if not name:
            if cur is not None:
                cur["signals"].append(row)
            continue
        finalize()
        cur = None
        where = str(row.get("source_cell") or row.get("location") or "")
        model, by_manufacturer = head_model(row, dtd)
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
        if by_manufacturer:
            findings.append(_f("sycon_model_by_manufacturer", "INFO", "station %r has no Part No.: keyed by its manufacturer "
                               "%r (%s)" % (name, model, rec["catalog_item"]), where))
        net = network_of(ip)
        # one project = one cifX card = one PROFINET network, the card's controller's (2026-10-24: the conveyor list's
        # two cabinet sheets are two networks, 192.168.2.x and 192.168.3.x, each with its own cifX card, and the
        # second repeats the first's station names - merged into one project they blocked the SYCON.net controller
        # dialog): the other cards' controllers and stations are INFO findings here, built by their own card
        if rec["role"] == "controller":
            if chosen is not None and controller is None and name.lower() == chosen["name"].lower():
                controller, controller_net = name, net
            else:
                other = next((c for c in cards if net is not None and c["net"] == net), None)
                if chosen is not None and net == chosen["net"]:
                    why = " (a second card on its network)"
                elif other is not None:
                    why = " - card %d's controller, its own project" % other["card"]
                else:
                    why = " - another PROFINET network"
                findings.append(_f("sycon_second_controller", "INFO", "station %r (%s, %s) skipped: the controller is %r%s"
                                   % (name, model, ip, chosen["name"] if chosen else controller, why), where))
                continue
        elif chosen is not None and net is not None and net != chosen["net"]:
            other = next((c for c in cards if c["net"] == net), None)
            findings.append(_f("sycon_other_network", "INFO", "station %r (%s, %s) is on another PROFINET network than the "
                               "controller %r - %s" % (name, model, ip, chosen["name"],
                                                      "card %d's project" % other["card"] if other else "no card's network"), where))
            continue
        # a duplicate name of station or IP among the slaves of one network is a document error: SYCON.net refuses the
        # second - a FAIL, the second station left out so the rest of the project can still be built
        elif name.lower() in seen_names:
            findings.append(_f("sycon_duplicate_name", "FAIL", "station %r (%s) is a second node with that PROFINET "
                               "name (the first: %s) - not exported" % (name, model, seen_names[name.lower()]), where))
            continue
        elif ip and ip in seen_ips:
            findings.append(_f("sycon_duplicate_ip", "FAIL", "station %r (%s) repeats the IP %s of %r - not exported"
                               % (name, model, ip, seen_ips[ip]), where))
            continue
        if rec["role"] != "controller":
            seen_names[name.lower()] = where or name
            if ip:
                seen_ips[ip] = name
        # a switch's updating time is left to the device (SYCON.net offers a SCALANCE 128 / 256 / 512 ms only,
        # 2026-10-23 21:36): the column stays empty for the controller and the `scalance-pnio` stations
        no_timing = rec["role"] == "controller" or rec["modules"] == "scalance-pnio"
        station = {"role": rec["role"], "station_name": name, "catalog_kind": ROLES[rec["role"]],
                   "catalog_item": rec["catalog_item"], "model_id": model, "gsdml": rec["gsdml"], "ip_address": ip,
                   "subnet_mask": DEFAULT_MASK, "gateway": "",
                   "update_time_ms": "" if no_timing else str(update_time_ms),
                   "device_number": str(row.get("id_node") or "").strip(),
                   "description": " ".join(str(row.get("description_module") or "").split()),
                   "comment": " ".join(str(row.get("manufacturer") or "").split()),
                   "symbolic_name": "" if rec["role"] == "controller" else symbolic_name(rec.get("symbolic", "default"), row, ip),
                   "fld": str(row.get("combined_FLD") or row.get("iol_FLD") or "").strip() or
                          (str(row.get("functional_unit") or "") + str(row.get("location") or "") + str(row.get("device") or "")).strip()}
        stations.append(station)
        cur = {"name": name, "rec": rec, "head_tag": str(row.get("slot") or "").strip(), "signals": [], "where": where,
               "station": station, "row": row}
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


def project(rows, out_dir: str, dtd_path: str | None = None, source_label: str = "signals",
            update_time_ms=DEFAULT_UPDATE_TIME_MS, card: int = 0) -> dict:
    """Build and write the handoff of every cifX card of the list (of `card` alone when given), one folder per
    card as the production folder of the sorter PC has it: `<out_dir>/HilscherIOCard<n>/SyconNetProjectInterface/`
    holds the three files of card n (Sycon5App builds `HilscherIOCard<n>/HilscherPnCard_<n>.spj` beside them).
    Returns {'dir', 'cards': [{card, project, dir, stations, modules, controller, paths..., findings}], the totals
    'stations' / 'modules', the findings of all cards (deduplicated), and card 1's paths and controller under the
    flat keys of the single-card days}."""
    dtd_path = dtd_path or SYCON_DTD_DEFAULT
    dtd = load_dtd(dtd_path)
    numbers = [card] if card else ([c["card"] for c in cards_of(rows, dtd)] or [1])
    cards, findings, seen = [], [], set()
    for n in numbers:
        stations, modules, card_findings = build(rows, dtd, update_time_ms, card=n)
        folder = os.path.join(out_dir, CARD_FOLDER % n, FOLDER)
        spath = _write(folder, STATIONS_FILE, _csv(KIND_STATIONS, STATIONS_HDR, stations, STATIONS_KEYS, source_label))
        mpath = _write(folder, MODULES_FILE, _csv(KIND_MODULES, MODULES_HDR, modules, MODULES_KEYS, source_label))
        dpath = _ship_dtd(folder, dtd_path)
        for f in card_findings:
            key = (f.type, f.detail, f.location)
            if key not in seen:
                seen.add(key)
                findings.append(f)
        cards.append({"card": n, "project": PROJECT_NAME % n, "dir": folder, "stations": len(stations),
                      "modules": len(modules), "stations_path": spath, "modules_path": mpath, "device_types_db": dpath,
                      "findings": card_findings,
                      "controller": next((s["station_name"] for s in stations if s["role"] == "controller"), "")})
    first = cards[0]
    return {"dir": out_dir, "cards": cards, "stations": sum(c["stations"] for c in cards),
            "modules": sum(c["modules"] for c in cards), "stations_path": first["stations_path"],
            "modules_path": first["modules_path"], "device_types_db": first["device_types_db"], "findings": findings,
            "controller": first["controller"]}


def stage_rows(iolist_path: str, sheet: str = "") -> tuple:
    """Stage an I/O List with the active configuration (the builtin params with the path swapped in) and return
    (its signal rows in document order, the staging findings); `sheet` keeps the rows of one source sheet only
    (a list with one cabinet sheet per cifX card, e.g. the chutes' R5.S1.C1 / C2 / C3: one project per card)."""
    from pipeline5.phases.staging import iolist as staging
    params = dict(config.load_params() or {})
    params["iolist_path"] = iolist_path
    database, findings = staging.stage_iolist(params, save=False)
    rows = list(database["signals"]) if "signals" in database else []
    if sheet:
        rows = [r for r in rows if str(r.get("source_sheet") or "").strip().lower() == sheet.strip().lower()]
    return rows, findings


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="write the SYCON.net handoff of an I/O List")
    p.add_argument("--iolist", required=True)
    p.add_argument("--out", required=True, help="the SyconNetProjectInterface folder to write")
    p.add_argument("--dtd", default="", help="the SYCON device-types database (default: Shared/HardwareConfigBuilderData)")
    p.add_argument("--update-time-ms", type=int, default=DEFAULT_UPDATE_TIME_MS, help="every station's PROFINET updating time")
    p.add_argument("--sheet", default="", help="one source sheet only (the rows of one cabinet sheet)")
    p.add_argument("--card", type=int, default=0, help="one cifX card only (1-based, in document order); default: every card")
    a = p.parse_args(argv)
    rows, findings = stage_rows(a.iolist, a.sheet)
    label = os.path.basename(a.iolist) + (" [%s]" % a.sheet if a.sheet else "")
    res = project(rows, a.out, a.dtd or None, source_label=label, update_time_ms=a.update_time_ms, card=a.card)
    for f in findings + res["findings"]:
        print("[%s] %s - %s  @ %s" % (f.severity, f.type, f.detail, f.location))
    for c in res["cards"]:
        print("SYCON handoff card %d (%s): %d stations (controller %r) + %d module rows -> %s" % (
            c["card"], c["project"], c["stations"], c["controller"], c["modules"], c["dir"]))
    return 1 if any(f.severity == "FAIL" for f in res["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
