"""Phase 700 (Hardware) build - clean-room port of PL3's `hardware.extract` into PL4's SSOT model.

A single ordered pass over the `signals` table populates two tables: **`hardware_stations`** (one row per
generatable head - a PLC / PlcCardCm / IoDevice) and **`hardware_modules`** (the IoDevice cards). The
`HardwareConfiguration/Stations.csv` + `Modules.csv` BuilderData surface is a pure projection of these
tables (phase 700b, `domain/hardware_csv.py`).

A head row (Script Type `PLC` -> Plc, `PlcCardCm` -> PlcCardCm, or Type col-R first letter `P` -> IoDevice)
opens a station; the rows after it (until the next head) are its signals. A head whose model (Part No) is
not in the DeviceTypesDatabase can't be generated -> a **`hw_device_not_in_dtd` FAIL** (a
**`hw_switch_not_in_dtd` WARN** for a switch), and the station is skipped.

- **Station**: name = Profinet name, Model Id = Part No (spaces stripped), Subnet from the IP, group =
  `<FunctionalUnit>_IODevices`. Custom Parameters = the DTD "I/O Addresses Parameter" (`%I%`/`%Q%` -> the
  device start byte, `+N` arithmetic) then the I/O List col-AG params (override, last).
- **Modules** (IoDevice only): signal rows grouped into cards by Slot (col E); a card whose Slot == the
  device's own tag is the TIA-auto-plugged card and is skipped. I Addr = Q Addr = the card start byte;
  Comment = the DTD comment. Custom Parameters = `PotentialGroup=1` on the first card + the DTD "Parameters
  by Signal Type" blocks (`Ch(#)` -> the signal's channel) then col-AG (override, last). Default cards
  (DTD ids `<PARENT>:SUFFIX`) add one row per station of PARENT.

DTD col-5 "Parameters" are applied by OP4 itself and are NEVER written here; only col-6 "Parameters by
Signal Type", col-7 "I/O Addresses Parameter", and I/O List col-AG are written, AG last.
"""
from __future__ import annotations

import re

from pipeline4.core import config, run
from pipeline4.core.database import Database
from pipeline4.core.finding import Finding, record
from pipeline4.core.table import Table
from pipeline4.domain.signals import signals_table

HEAD_PLC = "PLC"
HEAD_CM = "PLCCARDCM"
_ADDR = re.compile(r"\s*([IQ])\s*(\d+)\.(\d+)", re.IGNORECASE)


def _f(type: str, severity: str, detail: str, location: str = "", source_uid: str = "") -> Finding:
    """A phase-700 Finding - the hardware report container (the missing-DTD FAIL / switch WARN)."""
    return Finding(phase=700, type=type, severity=severity, detail=detail,
                   location=location, source_uid=source_uid)


# --- the SSOT tables ----------------------------------------------------------------------------- #
def hardware_stations_table() -> Table:
    """One row per generatable head (Plc / PlcCardCm / IoDevice). The `Stations.csv` projection (700b)
    maps these snake_case columns to the format-2 headers."""
    return Table(
        "hardware_stations",
        columns=["uid", "role", "station_name", "model_id", "ip_address", "pn_number", "subnet",
                 "custom_parameters", "group_path", "source_signal"],
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


def _role(row):
    s = str(row.get("script_type") or "").strip().upper()
    if s == HEAD_PLC:
        return "Plc"
    if s == HEAD_CM:
        return "PlcCardCm"
    if str(row.get("type_hw") or "").strip()[:1].upper() == "P":
        return "IoDevice"
    return None


def parse_address(value):
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


def _resolve_addr_template(template, i_base, q_base) -> str:
    """Replace %I%/%Q% (with optional +N) by the device start bytes."""
    def repl(m):
        sym, plus = m.group(1).upper(), m.group(2)
        base = i_base if sym == "I" else q_base
        if base is None:
            return m.group(0)
        return str(base + (int(plus) if plus else 0))
    return re.sub(r"%([IQ])%\s*(?:\+\s*(\d+))?", repl, template or "")


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


# --- the single-pass extract -> snake_case station/module rows + findings ------------------------ #
def extract(rows, dtd) -> tuple:
    """One ordered pass -> (stations, modules, findings). A head with no DTD model is a
    `hw_device_not_in_dtd` FAIL (`hw_switch_not_in_dtd` WARN for a switch) and the station is skipped."""
    by_id, default_cards = dtd["by_id"], dtd["default_cards"]
    stations, modules, findings = [], [], []
    cur = None

    def finalize():
        if cur is None:
            return
        row, model, rec = cur["row"], cur["model"], cur["rec"]
        sig_i = [a[1] for s in cur["signals"] if (a := parse_address(s.get("bit"))) and a[0] == "I"]
        sig_q = [a[1] for s in cur["signals"] if (a := parse_address(s.get("bit"))) and a[0] == "Q"]
        i_base = min(sig_i) if sig_i else None
        q_base = min(sig_q) if sig_q else None

        io_addr = _resolve_addr_template(rec["io_addr_params"], i_base, q_base)
        station_params = _merge_params(io_addr, str(row.get("hardware_params") or ""))
        stations.append({
            "role": cur["role"], "station_name": str(row.get("profinet_name") or "").strip(),
            "model_id": model, "ip_address": str(row.get("profinet_ip") or "").strip(),
            "pn_number": "", "subnet": _subnet(row.get("profinet_ip")),
            "custom_parameters": station_params,
            "group_path": str(row.get("functional_unit") or "").strip() + "_IODevices",
            "source_signal": str(row.get("uid", "")),
        })
        if cur["role"] != "IoDevice":
            return

        cards, order = {}, []
        for s in cur["signals"]:
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

    for row in rows or []:
        role = _role(row)
        if role is not None:
            finalize()
            model = _model_id(row.get("part_no"))
            rec = by_id.get(model.upper())
            if rec is None:                                   # not in the DTD -> can't generate
                sheet = row.get("source_sheet")
                loc = f"[{sheet}] row {row.get('source_row')}" if sheet else f"row {row.get('source_row')}"
                where = f"{loc} {row.get('profinet_name') or row.get('device') or ''}".strip()
                if _looks_like_switch(row):
                    findings.append(_f("hw_switch_not_in_dtd", "WARN",
                                       f"switch model {model!r} not in DeviceTypesDatabase - skipped",
                                       where, str(row.get("uid", ""))))
                else:
                    findings.append(_f("hw_device_not_in_dtd", "FAIL",
                                       f"device model {model!r} not in DeviceTypesDatabase - skipped",
                                       where, str(row.get("uid", ""))))
                cur = None
                continue
            cur = {"role": role, "row": row, "model": model, "rec": rec,
                   "head_tag": str(row.get("slot") or "").strip(), "signals": []}
        elif cur is not None:
            cur["signals"].append(row)
    finalize()
    return stations, modules, findings


def _fill_stations(table, stations) -> None:
    for s in stations:
        table.add(role=s["role"], station_name=s["station_name"], model_id=s["model_id"],
                  ip_address=s["ip_address"], pn_number=s["pn_number"], subnet=s["subnet"],
                  custom_parameters=s["custom_parameters"], group_path=s["group_path"],
                  source_signal=s["source_signal"])


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
    stations, modules, findings = extract(rows, config.load_device_types_db())
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
