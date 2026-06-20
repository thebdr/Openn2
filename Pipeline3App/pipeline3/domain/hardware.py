"""Hardware Generation (phase 700): format-2 Stations.csv + Modules.csv from the staged database.

A single ordered pass over ctx.rows: a head row (Script Type PLC -> Plc, PlcCardCm -> PlcCardCm, or
Type (col R) first letter P -> IoDevice) opens a station; the rows after it (until the next head) are
its signals. A head whose model (Part No) isn't in the DeviceTypesDatabase can't be generated -> an
ERROR (a WARNING for switches), and the station is skipped.

- **Station**: Name = Profinet name, Model Id = Part No (spaces stripped), Subnet from the IP,
  Group = "<FunctionalUnit>_IODevices". Custom Parameters = the DTD "I/O Addresses Parameter"
  (%I%/%Q% -> the device start byte, +N arithmetic) then the I/O List col-AG params (override, last).
- **Modules** (IoDevice only): signal rows grouped into cards by Slot (col E); a card whose Slot == the
  device's own tag is the TIA-auto-plugged card and is skipped. I Addr = Q Addr = the card's start
  byte; Comment = the DTD comment. Custom Parameters = PotentialGroup=1 on the first card + the DTD
  "Parameters by Signal Type" blocks (Ch(#) -> the signal's channel) then col-AG (override, last).
  Default cards (DTD ids "<PARENT>:SUFFIX") add one Modules row per station of PARENT.

DTD col-5 "Parameters" are applied by Open2App itself and are NEVER written here; only col-6
"Parameters by Signal Type", col-7 "I/O Addresses Parameter", and I/O List col-AG are written, AG
last. Output is comma format-2 matching the committed reference (Shared/.../TestData/Passing) - no BOM,
CRLF, a "#!format=2" tag line + a "# <descriptive headers>" comment. Clean-room rebuild of Pipeline2's
core/hardware.py (reference for INTENT only).
"""
from __future__ import annotations
import csv
import io
import os
import re

from pipeline3.core import config

HEAD_PLC = "PLC"
HEAD_CM = "PLCCARDCM"
_ADDR = re.compile(r"\s*([IQ])\s*(\d+)\.(\d+)", re.IGNORECASE)


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


def extract(rows, dtd):
    """One ordered pass -> (stations, modules, messages). messages are (level, text); a head with no
    DTD model is an ERROR (WARNING for a switch) and the station is skipped."""
    by_id, default_cards = dtd["by_id"], dtd["default_cards"]
    stations, modules, messages = [], [], []
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
            "Role": cur["role"], "Station Name": str(row.get("profinet_name") or "").strip(),
            "Model Id": model, "IP Address": str(row.get("profinet_ip") or "").strip(),
            "PN Number": "", "Subnet": _subnet(row.get("profinet_ip")),
            "Custom Parameters": station_params,
            "Group": str(row.get("functional_unit") or "").strip() + "_IODevices",
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
                "Station Name": str(row.get("profinet_name") or "").strip(),
                "Slot": plug, "Module Name": slot, "Model Id": cmodel,
                "I Addr": start, "Q Addr": start,
                "Custom Parameters": _merge_params(pg, by_type, card_ag),
                "Comment": crec["comment"] if crec else "",
            })

        for card_id in default_cards.get(model.upper(), []):   # default cards (<PARENT>:SUFFIX)
            crec = by_id[card_id.upper()]
            plug += 1
            modules.append({
                "Station Name": str(row.get("profinet_name") or "").strip(),
                "Slot": plug, "Module Name": crec["model_id"], "Model Id": crec["model_id"],
                "I Addr": "", "Q Addr": "", "Custom Parameters": "", "Comment": crec["comment"],
            })

    for row in rows or []:
        role = _role(row)
        if role is not None:
            finalize()
            model = _model_id(row.get("part_no"))
            rec = by_id.get(model.upper())
            if rec is None:                                   # not in the DTD -> can't generate
                sheet = row.get("_source_sheet")
                loc = f"[{sheet}] row {row.get('_source_row')}" if sheet else f"row {row.get('_source_row')}"
                where = f"{loc} {row.get('profinet_name') or row.get('device') or ''}".strip()
                if _looks_like_switch(row):
                    messages.append(("WARNING", f"{where}: switch model '{model}' not in DeviceTypesDatabase - skipped"))
                else:
                    messages.append(("ERROR", f"{where}: device model '{model}' not in DeviceTypesDatabase - skipped"))
                cur = None
                continue
            cur = {"role": role, "row": row, "model": model, "rec": rec,
                   "head_tag": str(row.get("slot") or "").strip(), "signals": []}
        elif cur is not None:
            cur["signals"].append(row)
    finalize()
    return stations, modules, messages


# --- format-2 output (matching the committed reference: no BOM, CRLF, descriptive headers) -------- #

_STATIONS_KEYS = ["Role", "Station Name", "Model Id", "IP Address", "PN Number", "Subnet",
                  "Custom Parameters", "Group"]
_STATIONS_FMT2 = "#!format=2,,,,,,,,"
_STATIONS_HDR = ("# Role,Station Name,Model Id,IP Address,PN Number (empty:last IP Octet),Subnet,"
                 "Custom Parameters (separator= | ), Group = folder/subfolder/...,")

_MODULES_KEYS = ["Station Name", "Slot", "Module Name", "Model Id", "I Addr", "Q Addr",
                 "Custom Parameters", "Comment"]
_MODULES_FMT2 = "#!format=2,,,,,,,"
_MODULES_HDR = ("# Station Name,Slot (plug order),Module Name,Model Id,I Addr,Q Addr,"
                "Custom Parameters (separator= | )  syntax: [Item(i).][Ch(i).]Name=Value,Comment")


def _format2(fmt2_line, header_line, rows, keys) -> str:
    """Comma format-2 text (CRLF): the '#!format=2' tag, the '# <headers>' comment, then one
    csv-quoted row per dict (QUOTE_MINIMAL; params use '|' so they don't need quoting)."""
    buf = io.StringIO()
    buf.write(fmt2_line + "\r\n")
    buf.write(header_line + "\r\n")
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows:
        w.writerow([str(r.get(k, "")) for k in keys])
    return buf.getvalue()


def _write(out_root, filename, text) -> str:
    hw = config.out_path(out_root, "hardware_dir")
    os.makedirs(hw, exist_ok=True)
    path = os.path.join(hw, filename)
    with open(path, "w", encoding="utf-8", newline="") as f:    # no BOM, CRLF (matches the reference)
        f.write(text)
    return path


def write_stations(stations, out_root) -> str:
    return _write(out_root, "Stations.csv", _format2(_STATIONS_FMT2, _STATIONS_HDR, stations, _STATIONS_KEYS))


def write_modules(modules, out_root) -> str:
    return _write(out_root, "Modules.csv", _format2(_MODULES_FMT2, _MODULES_HDR, modules, _MODULES_KEYS))


def generate(rows, out_root, dtd) -> dict:
    """710+720 entry: one extract -> Stations.csv + Modules.csv. Returns {'dir', 'stations',
    'modules', 'messages', 'errors', 'stations_path', 'modules_path'}."""
    stations, modules, messages = extract(rows, dtd)
    spath = write_stations(stations, out_root)
    mpath = write_modules(modules, out_root)
    return {"dir": config.out_path(out_root, "hardware_dir"),
            "stations": len(stations), "modules": len(modules),
            "messages": messages, "errors": [m for m in messages if m[0] == "ERROR"],
            "stations_path": spath, "modules_path": mpath}
