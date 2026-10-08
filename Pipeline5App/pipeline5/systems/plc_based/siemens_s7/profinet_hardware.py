"""Phase 700 (Hardware) build - clean-room port of PL3's `hardware.extract` into PL4's SSOT model.

A single ordered pass over the `signals` table populates two tables: **`hardware_stations`** (one row per
generatable head - a PLC / PlcCardCm / IoDevice) and **`hardware_modules`** (the IoDevice cards). The
`HardwareConfiguration/Stations.csv` + `Modules.csv` BuilderData surface is a pure projection of these
tables (phase 700b, `domain/hardware_csv.py`).

A head row (Script Type `PLC` -> Plc, `PlcCardCm` -> PlcCardCm, or Type col-R first letter `P` -> IoDevice)
opens a station; the rows after it (until the next head) are its signals. A head whose model (Part No) is
not in the DeviceTypesDatabase can't be generated -> a **`hw_device_not_in_dtd` FAIL** (a
**`hw_switch_not_in_dtd` WARN** for a switch), and the station is skipped.

A head whose IP is ALREADY a generated station's is skipped too - only the FIRST station per IP is
generated (TIA rejects two devices on one IP; a redundant-CPU pair documents Master + Backup on the same
address). The skip is a **`hw_duplicate_ip` WARN** - downgraded to **INFO** when the head's module
description mentions "backup" (the documented, expected redundancy case). The finding links the skipped
head's I/O-List row (`location`) and the generated station's (`location2`); the detail text is IDENTICAL
for both severities, so the uid - which excludes severity - survives a description edit that flips the
level. Note: doc-validation 110 deliberately exempts `.1`-suffixed IPs from `ip_duplicated`, so this
build-side skip is where the redundant-CPU pair is handled.

A model's station I/O address template (DTD col 7, `%I%`/`%Q%`[+N]) is placed at the station's LOWEST I/O-List
address per direction. A direction with no row leaves its entries unplaceable: they are DROPPED (never written as
a literal `%Q%` the importer cannot convert) with a **`hw_addr_unresolved` WARN** - TIA places that submodule.

- **Station**: name = Profinet name, Model Id = Part No (spaces stripped), Subnet from the IP, group =
  `<FunctionalUnit>_IODevices` - EMPTY for the Plc head (the PLC stays at the TIA root; OP honors Group
  for every row, 2026-07-07). Custom Parameters = the DTD "I/O Addresses Parameter" (`%I%`/`%Q%` -> the
  device start byte, `+N` arithmetic) then the I/O List col-AG params (override, last). Connector = the
  head row's `connector` cell VERBATIM (col I; appended to Stations.csv as the LAST column, 2026-07-06).
- **Modules** (IoDevice only): signal rows grouped into cards by Slot (col E); a card whose Slot == the
  device's own tag is the TIA-auto-plugged card and is skipped. I Addr = Q Addr = the card start byte;
  Comment = the DTD comment. Custom Parameters = `PotentialGroup=1` on the first card + the DTD "Parameters
  by Signal Type" blocks (`Ch(#)` -> the signal's channel) then col-AG (override, last). Default cards
  (DTD ids `<PARENT>:SUFFIX`) add one row per station of PARENT.
- **Transfer areas** ([[C-031]]): an IOC row (an interface) under a coupler's head is never a card - the coupler
  gets `<name>_IN` (TransferArea-IN, I Addr = the IOC base) and `<name>_OUT` (TransferArea-OUT, Q Addr = the
  base) per interface, positions 1..n, after the cards; the area length is the model's DTD default (applied by
  the importer) unless the IOC row's col AG sets that area's length key (written, routed to its area).

DTD col-5 "Parameters" are applied by OP4 itself and are NEVER written here; only col-6 "Parameters by
Signal Type", col-7 "I/O Addresses Parameter", and I/O List col-AG are written, AG last.

Place in the flow: the 700 header / 710 "Generate Stations" / 720 "Generate Modules" (run_hardware
in src://pipeline5/systems/plc_based/siemens_s7/safety/main.py; both subs share this one build -
only the label differs, like PL3). Reads the `signals` SSOT table + the DeviceTypesDatabase
(`load_device_types_db` in src://pipeline5/config/loaders.py); writes the `hardware_stations` +
`hardware_modules` SSOT tables and records the findings to `validation_issues`. The CSV projection
is src://pipeline5/systems/plc_based/siemens_s7/hardware_csv_export.py (700b).

Decision history: the duplicate-IP skip and the Connector column are both production fixes from
the FVX pilot (2026-07-06, user spec) - the skip handles the documented redundant-CPU Master+Backup
pair on one address, the Connector carries the col-I port designation (`X1-P1 R`) OP4 extracts.
"""
from __future__ import annotations

import os
import re

from pipeline5 import config
from pipeline5.findings import gate as run
from pipeline5.truth.database import Database
from pipeline5.findings.finding import Finding, record
from pipeline5.truth.table import Table
from pipeline5.truth.signals import signals_table, is_generated, station_role
from pipeline5.truth.identity import INTERFACE_TRIGGER_TYPE
from pipeline5.phases.interfaces.builder import (TRANSFER_AREAS, area_params, base_byte, interface_name, ioc_base,
                                                length_value)

_ADDR = re.compile(r"\s*([IQ])\s*(\d+)\.(\d+)", re.IGNORECASE)


def _f(type: str, severity: str, detail: str, location: str = "", source_uid: str = "", doc: str = "",
       location2: str = "", doc2: str = "") -> Finding:
    """A phase-700 Finding - the hardware report container (the missing-DTD FAIL / switch WARN + the
    duplicate-IP skip, whose location/location2 pair links the skipped head and the generated station)."""
    return Finding(phase=700, type=type, severity=severity, detail=detail,
                   location=location, source_uid=source_uid, doc=doc, location2=location2, doc2=doc2)

def _io_doc() -> str:
    """The I/O List basename - the GUI log resolves it back to the open document for the clickable
    Sheet!Cell links (findings pointing at DOC ROWS must carry location=source_cell + this doc)."""
    try:
        return os.path.basename(str(config.load_params().get("iolist_path") or ""))
    except Exception:  # noqa: BLE001 - a missing/broken params file must not break the build
        return ""



# --- the SSOT tables ----------------------------------------------------------------------------- #
def hardware_stations_table() -> Table:
    """One row per generatable head (Plc / PlcCardCm / IoDevice). The `Stations.csv` projection (700b)
    maps these snake_case columns to the format-2 headers."""
    return Table(
        "hardware_stations",
        columns=["uid", "role", "station_name", "model_id", "ip_address", "pn_number", "subnet",
                 "custom_parameters", "group_path", "connector", "source_signal"],
        json_columns=[],
        key_columns=["station_name", "model_id"],
    )


def hardware_modules_table() -> Table:
    """One row per IoDevice card (in plug order) - the `Modules.csv` projection source (700b)."""
    return Table(
        "hardware_modules",
        columns=["uid", "station_name", "slot", "module_name", "model_id", "i_addr", "q_addr",
                 "custom_parameters", "comment", "source_signal"],
        json_columns=[],
        # module_name (the electrical slot tag) is the stable identity; model_id disambiguates the (absurd
        # but possible) case of a DTD default-card id equal to a real card's slot tag -> collision-proof.
        key_columns=["station_name", "module_name", "model_id"],
    )


# --- helpers (ported from PL3 hardware.py) ------------------------------------------------------- #
def _model_id(part_no) -> str:
    return str(part_no or "").replace(" ", "").strip()


def _subnet(ip) -> str:
    p = str(ip or "").split(".")
    return f"Subnet{p[2]}" if len(p) == 4 else ""


_role = station_role                      # the head rule every positional reader shares (truth/signals.py)


def plc_station_name(rows) -> str:
    """The Plc head's station name - its PROFINET name, exactly what Stations.csv calls it (and so the
    PLC folder of the OP5 workspace, contract v1 §4) - among staged signal rows; '' when none."""
    for row in rows:
        if _role(row) == "Plc":
            name = str(row.get("profinet_name") or "").strip()
            if name:
                return name
    return ""


def parse_address(value):
    """An I/O-List `bit` cell -> the ('I'|'Q', byte, bit) triple, e.g. 'I 12.3' -> ('I', 12, 3);
    None when the cell isn't an I/Q dotted address (a blank / a head row)."""
    m = _ADDR.match(str(value or ""))
    return (m.group(1).upper(), int(m.group(2)), int(m.group(3))) if m else None


def _merge_params(*blobs) -> str:
    """Merge '|'-separated 'key=value' params; later blobs override by key (text before '='). Order
    preserved by first appearance; a valueless token (a bare flag) is kept once."""
    order, values = [], {}
    for blob in blobs:
        for part in str(blob or "").split("|"):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                if part not in values:
                    order.append(part)
                    values[part] = None
                continue
            key = part.split("=", 1)[0].strip()
            if key not in values:
                order.append(key)
            values[key] = part
    return " | ".join(values[k] if values[k] is not None else k for k in order)


_UNRESOLVED_RX = re.compile(r"%([IQ])%", re.IGNORECASE)
_KEY_RANGE_RX = re.compile(r"\((\d+)-(\d+)\)")


def _param_keys(key: str) -> set:
    """A parameter key as the importer (Openn3App's CustomParameterParser) reads it: each `.` step trimmed, case
    ignored, ONE `(a-b)` range expanded - `Item(0).Addr(0-1).StartAddress` sets Addr(0) AND Addr(1)."""
    k = ".".join(step.strip() for step in str(key).split(".")).strip().lower()
    m = _KEY_RANGE_RX.search(k)
    if not m:
        return {k}
    a, b = sorted((int(m.group(1)), int(m.group(2))))
    return {f"{k[:m.start()]}({i}){k[m.end():]}" for i in range(a, b + 1)}


def _resolve_addr_template(template, i_base, q_base) -> str:
    """Replace %I%/%Q% (with optional +N) by the device start bytes."""
    def repl(m):
        sym, plus = m.group(1).upper(), m.group(2)
        base = i_base if sym == "I" else q_base
        if base is None:
            return m.group(0)
        return str(base + (int(plus) if plus else 0))
    return re.sub(r"%([IQ])%\s*(?:\+\s*(\d+))?", repl, template or "", flags=re.IGNORECASE)


def _channel(addr, card_start_byte) -> int:
    _, byte, bit = addr
    return (byte - card_start_byte) * 8 + bit


def _expand_by_type(card_signals, params_by_type, card_start_byte) -> str:
    """Per-signal 'Parameters by Signal Type' blocks, the Ch(#) placeholder -> the signal's channel."""
    parts = []
    for sig in card_signals:
        addr = parse_address(sig.get("bit"))
        if not addr:
            continue
        block = params_by_type.get(str(sig.get("script_type") or "").strip().upper())
        if not block:
            continue
        parts.append(block.replace("#", str(_channel(addr, card_start_byte))))
    return _merge_params(*parts)


def _looks_like_switch(row) -> bool:
    text = (str(row.get("description_module") or "") + " " + str(row.get("desc_l1") or "")).upper()
    return "SWITCH" in text


def _is_backup(row) -> bool:
    """A head documented as a redundancy partner ('backup' in its module description) - its duplicate-IP
    skip is the EXPECTED case (INFO), not a review condition (WARN)."""
    return "backup" in str(row.get("description_module") or "").lower()


def _where(row) -> str:
    """The row's log locator: `source_cell` (a LIVE Sheet!Cell link) when staged, else the descriptive
    `[<sheet>] row <n>` fallback (older stagings; no link)."""
    sheet = row.get("source_sheet")
    fallback = f"[{sheet}] row {row.get('source_row')}" if sheet else f"row {row.get('source_row')}"
    return str(row.get("source_cell") or "").strip() or fallback


def _is_ioc(row) -> bool:
    return str(row.get("script_type") or "").strip().upper() == INTERFACE_TRIGGER_TYPE


def _ioc_without_coupler(row, where_text) -> Finding:
    where = _where(row)
    return _f("hw_ta_no_iodevice", "WARN",
              f"interface {str(row.get('index') or '').strip()!r} {where_text}: no transfer area (an interface is an "
              "area of the coupler whose head it sits under - an I-device is not modelled)",
              where, str(row.get("uid", "")), doc=_io_doc() if "!" in where else "")


def _transfer_areas(station, head, iocs, by_id, findings) -> list:
    """A coupler's transfer-area module rows ([[C-031]]): per IOC row under its head, in document order,
    `<name>_IN` (TransferArea-IN, I Addr = the base) and `<name>_OUT` (TransferArea-OUT, Q Addr = the base),
    positions 1..n; the base = the IOC row's Bit, else the head's `coupler_start` (`ioc_base`). Lengths: the
    database model's default is applied by the importer - only the IOC row's own length key (Hardware Parameters,
    `area_params`: any spelling, the last entry winning) is written, in the database's spelling, on its own area;
    another entry is a `hw_ta_param_unrouted` WARN. Blocking: a base that is no byte (`hw_ta_base_invalid`), a
    length that is no positive whole number (`hw_ta_length_invalid`), a model missing from the database
    (`hw_device_not_in_dtd`)."""
    out, position = [], 0
    for ioc in iocs:
        name = interface_name(ioc.get("index"))
        if not name:                                    # 400 reports the IOC row without an Index
            continue
        where = _where(ioc)
        doc = _io_doc() if "!" in where else ""
        cell = ioc_base(ioc, head)
        base = base_byte(cell)
        if base is None:
            findings.append(_f("hw_ta_base_invalid", "FAIL",
                               f"interface {name!r} on {station!r}: base {cell!r} is not a byte (the IOC row's Bit - "
                               "`10000` or `I10000.0` - or its coupler's start) - its transfer areas cannot be placed",
                               where, str(ioc.get("uid", "")), doc=doc))
            continue
        lengths, unrouted = area_params(ioc.get("hardware_params"))
        invalid = [d for d, v in lengths.items() if v is not None and length_value(v) is None]
        if invalid:
            findings.append(_f("hw_ta_length_invalid", "FAIL",
                               f"interface {name!r} on {station!r}: "
                               + ", ".join(f"{TRANSFER_AREAS[d][1]}={lengths[d]!r}" for d in invalid)
                               + " in its Hardware Parameters is no positive whole number of bytes",
                               where, str(ioc.get("uid", "")), doc=doc))
            continue
        if unrouted:
            findings.append(_f("hw_ta_param_unrouted", "WARN",
                               f"interface {name!r} on {station!r}: Hardware Parameters entr"
                               + ("y " if len(unrouted) == 1 else "ies ") + " | ".join(unrouted)
                               + " name no transfer area (only " + " / ".join(k for _m, k in TRANSFER_AREAS.values())
                               + ") - not written", where, str(ioc.get("uid", "")), doc=doc))
        for direction, suffix in (("I", "_IN"), ("Q", "_OUT")):
            model = TRANSFER_AREAS[direction][0]
            rec = by_id.get(model.upper())
            if rec is None:
                findings.append(_f("hw_device_not_in_dtd", "FAIL",
                                   f"transfer-area model {model!r} (interface {name!r} on {station!r}) not in "
                                   "DeviceTypesDatabase - skipped", where, str(ioc.get("uid", "")), doc=doc))
                continue
            position += 1
            out.append({
                "station_name": station, "slot": position, "module_name": name + suffix,
                "model_id": rec["model_id"],
                "i_addr": base if direction == "I" else "", "q_addr": base if direction == "Q" else "",
                "custom_parameters": (f"{TRANSFER_AREAS[direction][1]}={length_value(lengths[direction])}"
                                      if lengths[direction] is not None else ""),
                "comment": rec["comment"],
                "source_signal": str(ioc.get("uid", "")),
            })
    return out


# --- the single-pass extract -> snake_case station/module rows + findings ------------------------ #
def extract(rows, dtd) -> tuple:
    """One ordered pass -> (stations, modules, findings). A head with no DTD model is a
    `hw_device_not_in_dtd` FAIL (`hw_switch_not_in_dtd` WARN for a switch) and the station is skipped.
    A head whose IP a GENERATED station already uses is skipped too (only the first per IP is generated)
    - a `hw_duplicate_ip` WARN, or INFO for a documented backup head (`_is_backup`); its signal rows are
    dropped with it (no station -> no cards)."""
    by_id, default_cards = dtd["by_id"], dtd["default_cards"]
    stations, modules, findings = [], [], []
    cur = None
    seen_ips = {}          # ip -> the FIRST generated station's {name, where} - the dedup anchor
    any_head = False       # an IOC row before the first head has no station
    skipped = ""           # the last head SKIPPED (duplicate IP / not in the DTD) - its IOC rows get no area either

    def finalize():
        if cur is None:
            return
        row, model, rec = cur["row"], cur["model"], cur["rec"]
        iocs = [s for s in cur["signals"] if _is_ioc(s)]        # interfaces: transfer areas, never cards / I/O
        io_rows = [s for s in cur["signals"] if not _is_ioc(s)]
        sig_i = [a[1] for s in io_rows if (a := parse_address(s.get("bit"))) and a[0] == "I"]
        sig_q = [a[1] for s in io_rows if (a := parse_address(s.get("bit"))) and a[0] == "Q"]
        i_base = min(sig_i) if sig_i else None
        q_base = min(sig_q) if sig_q else None

        io_addr = _resolve_addr_template(rec["io_addr_params"], i_base, q_base)
        # an entry whose %I%/%Q% found no base (the station has no row of that direction) is DROPPED, never
        # written as a literal the importer cannot read - TIA places that submodule itself ([[C-028]])
        kept = [e for e in (p.strip() for p in io_addr.split("|")) if e]
        unresolved = [e for e in kept if _UNRESOLVED_RX.search(e)]
        hw_params = str(row.get("hardware_params") or "")
        if unresolved:
            kept = [e for e in kept if e not in unresolved]
            io_addr = " | ".join(kept)
            # an entry the head's Hardware Parameters (col AG) set - with a value - is placed by them, not left to TIA;
            # keys compared the importer's way (round 3: case, spacing, one `(a-b)` range)
            ag_keys = set()
            for p in hw_params.split("|"):
                if "=" in p and p.split("=", 1)[1].strip():
                    ag_keys |= _param_keys(p.split("=", 1)[0])
            left = [e for e in unresolved if not _param_keys(e.split("=", 1)[0]) <= ag_keys]
            if left:
                where = _where(row)
                missing = sorted({m.group(1).upper() for e in left for m in _UNRESOLVED_RX.finditer(e)})
                findings.append(_f("hw_addr_unresolved", "WARN",
                                   f"station {str(row.get('profinet_name') or '').strip()!r} ({model}): no "
                                   + " / ".join({"I": "input", "Q": "output"}[d] for d in missing)
                                   + f" row to place {len(left)} start-address entr"
                                   + ("y" if len(left) == 1 else "ies") + " - left to TIA",
                                   where, str(row.get("uid", "")), doc=_io_doc() if "!" in where else ""))
        station_params = _merge_params(io_addr, hw_params)
        stations.append({
            "role": cur["role"], "station_name": str(row.get("profinet_name") or "").strip(),
            "model_id": model, "ip_address": str(row.get("profinet_ip") or "").strip(),
            "pn_number": "", "subnet": _subnet(row.get("profinet_ip")),
            "custom_parameters": station_params,
            # the PLC head stays at the TIA root (OP now honors Group for every row - a grouped Plc
            # would land inside its own device folder); the other stations keep the FU device group
            "group_path": ("" if cur["role"] == "Plc" else
                           str(row.get("functional_unit") or "").strip() + "_IODevices"),
            "connector": str(row.get("connector") or "").strip(),
            "source_signal": str(row.get("uid", "")),
        })
        if cur["role"] != "IoDevice":
            for s in iocs:
                findings.append(_ioc_without_coupler(s, f"under the {cur['role']} head "
                                                        f"{str(row.get('profinet_name') or '').strip()!r}"))
            return

        cards, order = {}, []
        for s in io_rows:
            slot = str(s.get("slot") or "").strip()
            if not slot or slot == cur["head_tag"]:          # auto-plugged card: the device's own tag
                continue
            if slot not in cards:
                cards[slot] = []
                order.append(slot)
            cards[slot].append(s)

        plug = 0
        for slot in order:
            sigs = cards[slot]
            cmodel = _model_id(sigs[0].get("part_no"))
            crec = by_id.get(cmodel.upper())
            bytes_ = [a[1] for s in sigs if (a := parse_address(s.get("bit")))]
            start = min(bytes_) if bytes_ else ""
            plug += 1
            pg = "PotentialGroup=1" if plug == 1 else ""     # first card starts a group; 2+ from col-AG
            by_type = _expand_by_type(sigs, crec["params_by_type"] if crec else {}, start if start != "" else 0)
            card_ag = _merge_params(*[str(s.get("hardware_params") or "") for s in sigs])
            modules.append({
                "station_name": str(row.get("profinet_name") or "").strip(),
                "slot": plug, "module_name": slot, "model_id": cmodel,
                "i_addr": start, "q_addr": start,
                "custom_parameters": _merge_params(pg, by_type, card_ag),
                "comment": crec["comment"] if crec else "",
                "source_signal": str(sigs[0].get("uid", "")),
            })

        for card_id in default_cards.get(model.upper(), []):   # default cards (<PARENT>:SUFFIX)
            crec = by_id[card_id.upper()]
            plug += 1
            modules.append({
                "station_name": str(row.get("profinet_name") or "").strip(),
                "slot": plug, "module_name": crec["model_id"], "model_id": crec["model_id"],
                "i_addr": "", "q_addr": "", "custom_parameters": "", "comment": crec["comment"],
                "source_signal": "",
            })

        modules.extend(_transfer_areas(str(row.get("profinet_name") or "").strip(), row, iocs, by_id, findings))

    for row in rows or []:
        if is_generated(row):                    # a generated signal sits under no head in the document - a
            if _is_ioc(row):                     # POSITIONAL walk never gives it to a station ([[C-030]] round 1)
                findings.append(_ioc_without_coupler(row, "generated (no document row - under no head)"))
            continue
        role = _role(row)
        if role is not None:
            any_head = True
            finalize()
            ip = str(row.get("profinet_ip") or "").strip()
            name = str(row.get("profinet_name") or row.get("device") or "").strip()
            if ip and ip in seen_ips:                         # a generated station already owns this IP
                first, where = seen_ips[ip], _where(row)
                io_doc = _io_doc()
                findings.append(_f("hw_duplicate_ip", "INFO" if _is_backup(row) else "WARN",
                                   f"duplicate IP {ip}"
                                   + (f" ({name})" if name else "")
                                   + f" - station skipped, only the first ('{first['name'] or first['where']}')"
                                   + " is generated",
                                   where, str(row.get("uid", "")), doc=io_doc if "!" in where else "",
                                   location2=first["where"],
                                   doc2=io_doc if "!" in first["where"] else ""))
                cur, skipped = None, name or _where(row)
                continue
            model = _model_id(row.get("part_no"))
            rec = by_id.get(model.upper())
            if rec is None:                                   # not in the DTD -> can't generate
                where = _where(row)                           # source_cell -> a LIVE link
                io_doc = _io_doc() if "!" in where else ""
                if _looks_like_switch(row):
                    findings.append(_f("hw_switch_not_in_dtd", "WARN",
                                       f"switch model {model!r}"
                                       + (f" ({name})" if name else "")
                                       + " not in DeviceTypesDatabase - skipped",
                                       where, str(row.get("uid", "")), doc=io_doc))
                else:
                    findings.append(_f("hw_device_not_in_dtd", "FAIL",
                                       f"device model {model!r}"
                                       + (f" ({name})" if name else "")
                                       + " not in DeviceTypesDatabase - skipped",
                                       where, str(row.get("uid", "")), doc=io_doc))
                cur, skipped = None, name or _where(row)
                continue
            cur = {"role": role, "row": row, "model": model, "rec": rec,
                   "head_tag": str(row.get("slot") or "").strip(), "signals": []}
            if ip:                                            # this head GENERATES -> it owns the IP
                seen_ips[ip] = {"name": name, "where": _where(row)}
        elif cur is not None:
            cur["signals"].append(row)
        elif _is_ioc(row):
            findings.append(_ioc_without_coupler(row, "before any station head" if not any_head
                                                 else f"under the skipped station {skipped!r}"))
    finalize()
    return stations, modules, findings


def _fill_stations(table, stations) -> None:
    for s in stations:
        table.add(role=s["role"], station_name=s["station_name"], model_id=s["model_id"],
                  ip_address=s["ip_address"], pn_number=s["pn_number"], subnet=s["subnet"],
                  custom_parameters=s["custom_parameters"], group_path=s["group_path"],
                  connector=s["connector"], source_signal=s["source_signal"])


def _fill_modules(table, modules) -> None:
    for m in modules:
        table.add(station_name=m["station_name"], slot=str(m["slot"]), module_name=m["module_name"],
                  model_id=m["model_id"], i_addr=str(m["i_addr"]), q_addr=str(m["q_addr"]),
                  custom_parameters=m["custom_parameters"], comment=m["comment"],
                  source_signal=m["source_signal"])


def build(database: Database | None = None) -> tuple:
    """Phase 700 (SSOT): extract the staged signals + the DeviceTypesDatabase -> the `hardware_stations`
    + `hardware_modules` tables. Loads the staged Database when none is passed; on a raw FAIL
    (`hw_device_not_in_dtd`) returns WITHOUT writing (`run.has_blocking` - the caller's `run.gate` halts).
    Records the findings to `validation_issues` + saves on success. Returns (database, findings)."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = Database([signals_table([m["canonical"] for m in colmap])]).load(config.database_dir())
    rows = list(database["signals"])
    # the project's own database when its params name one (`device_types_db`, [[C-028]] round 3), else the shared
    stations, modules, findings = extract(rows, config.load_device_types_db(config.load_params()))
    if run.has_blocking(findings):                  # raw-FAIL guard: never write BuilderData on a FAIL
        return database, findings

    stab, mtab = hardware_stations_table(), hardware_modules_table()
    _fill_stations(stab, stations)
    _fill_modules(mtab, modules)
    for table in (stab, mtab):
        if table.name in database:
            database[table.name].rows = table.rows
        else:
            database.add_table(table)
    record(database, findings)                      # persist the facts to the validation_issues table
    database.save(config.database_dir())
    return database, findings
