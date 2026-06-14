"""Hardware: extract format-2 Stations.csv + Modules.csv from the I/O List.

Deduced rules (golden: HardwareConfig/{Stations,Modules}.csv):
 Roles  - Script Type PLC/PlcCardCm = heads; Type (R) first letter P = IoDevice.
 Filter - a head is emitted only if its model is in the DeviceTypesDatabase
          (so unlisted devices, e.g. managed switches, are skipped).
 Station- Name=Profinet name, Model Id=Part No (no spaces), PN empty (->last IP
          octet), Subnet from IP, Group=<FunctionalUnit>_IODevices.
          Custom Parameters = device DTD params + DTD "I/O Addresses Parameter"
          (%I%/%Q% = device start byte, +N arithmetic), then I/O List col AG
          (Hardware Parameters) overrides.
 Modules- signal rows grouped into cards by Slot (col E); a group whose Slot
          equals the device's own tag is the auto-plugged card and is skipped.
          I Addr = Q Addr = card start byte. Comment = DTD comment.
          Custom Parameters = PotentialGroup=1 when the card model changes from
          the previous card, + per-signal "Parameters by Signal Type" blocks
          (Ch(#) -> Ch(channel)), then col-AG overrides.
 Default cards - DTD entries '<PARENT>:SUFFIX' are emitted as extra Modules rows
          for every station of PARENT (with the default card's DTD params).

Override order honored throughout: I/O List (col AG) params are written last.
"""
from __future__ import annotations
import csv
import io
import os
import re

HEAD_PLC = "PLC"
HEAD_CM = "PLCCARDCM"
_ADDR = re.compile(r"\s*([IQ])\s*(\d+)\.(\d+)", re.IGNORECASE)


def _model_id(part_no) -> str:
    return str(part_no or "").replace(" ", "").strip()


def _subnet(ip: str) -> str:
    p = str(ip or "").split(".")
    return f"Subnet{p[2]}" if len(p) == 4 else ""


def _role(row) -> str | None:
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
    """Merge '|'-separated 'key=value' params; later blobs override by key
    (key = text before '='). Order preserved by first appearance."""
    order, values = [], {}
    for blob in blobs:
        for part in str(blob or "").split("|"):
            part = part.strip()
            if not part or "=" not in part:
                if part:  # a valueless token like a bare flag - keep once
                    if part not in values:
                        order.append(part)
                        values[part] = None
                continue
            key = part.split("=", 1)[0].strip()
            if key not in values:
                order.append(key)
            values[key] = part
    return " | ".join(values[k] if values[k] is not None else k for k in order)


def _resolve_addr_template(template: str, i_base, q_base) -> str:
    """Replace %I%/%Q% (with optional +N) by the device start bytes."""
    def repl(m):
        sym, plus = m.group(1).upper(), m.group(2)
        base = i_base if sym == "I" else q_base
        if base is None:
            return m.group(0)
        return str(base + (int(plus) if plus else 0))
    return re.sub(r"%([IQ])%\s*(?:\+\s*(\d+))?", repl, template or "")


def _channel(addr, card_start_byte) -> int:
    """Channel index of a signal on its card: (byte - start) * 8 + bit."""
    _, byte, bit = addr
    return (byte - card_start_byte) * 8 + bit


def _expand_by_type(card_signals, signal_types_by_type, card_start_byte) -> str:
    """Per-signal 'Parameters by Signal Type' blocks, Ch(#) -> Ch(channel)."""
    parts = []
    for sig in card_signals:
        addr = parse_address(sig.get("bit"))
        if not addr:
            continue
        st = str(sig.get("script_type") or "").strip().upper()
        block = signal_types_by_type.get(st)
        if not block:
            continue
        ch = _channel(addr, card_start_byte)
        parts.append(block.replace("#", str(ch)))
    return _merge_params(*parts)


def _looks_like_switch(row) -> bool:
    text = (str(row.get("description_module") or "") + " " + str(row.get("desc_l1") or "")).upper()
    return "SWITCH" in text


def extract(io_rows: list, dtd: dict):
    """Single pass over the I/O List -> (stations, modules, messages).
    messages: (level, text) - heads with no DTD model are ERROR, except switches
    (WARNING). Switches are not generatable stations and are skipped either way."""
    by_id = dtd["by_id"]
    default_cards = dtd["default_cards"]
    stations, modules, messages = [], [], []
    cur = None  # {role, row, model, rec, head_tag, signals[]}

    def finalize():
        if cur is None:
            return
        row, model, rec = cur["row"], cur["model"], cur["rec"]
        sig_i = [parse_address(s.get("bit"))[1] for s in cur["signals"]
                 if parse_address(s.get("bit")) and parse_address(s.get("bit"))[0] == "I"]
        sig_q = [parse_address(s.get("bit"))[1] for s in cur["signals"]
                 if parse_address(s.get("bit")) and parse_address(s.get("bit"))[0] == "Q"]
        i_base = min(sig_i) if sig_i else None
        q_base = min(sig_q) if sig_q else None

        # DTD col-5 (Parameters) is applied by Openn2 itself - NOT written here.
        # Station params: the resolved I/O-address template + I/O List col-AG (last).
        io_addr = _resolve_addr_template(rec["io_addr_params"], i_base, q_base)
        head_ag = str(row.get("hardware_params") or "")
        station_params = _merge_params(io_addr, head_ag)

        stations.append({
            "Role": cur["role"], "Station Name": str(row.get("profinet_name") or "").strip(),
            "Model Id": model, "IP Address": str(row.get("profinet_ip") or "").strip(),
            "PN Number": "", "Subnet": _subnet(row.get("profinet_ip")),
            "Custom Parameters": station_params,
            "Group": str(row.get("functional_unit") or "").strip() + "_IODevices",
        })

        if cur["role"] != "IoDevice":
            return

        # group signals into cards by Slot (col E), in order
        cards, order = {}, []
        for s in cur["signals"]:
            slot = str(s.get("slot") or "").strip()
            if not slot or slot == cur["head_tag"]:  # auto-plugged card: device's own tag
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
            bytes_ = [parse_address(s.get("bit"))[1] for s in sigs if parse_address(s.get("bit"))]
            start = min(bytes_) if bytes_ else ""
            plug += 1
            # PotentialGroup: the first card always starts a group; for slots 2+ it
            # comes from the I/O List (col AG) - the designer decides per module.
            pg = "PotentialGroup=1" if plug == 1 else ""
            by_type = _expand_by_type(sigs, crec["params_by_type"] if crec else {}, start if start != "" else 0)
            card_ag = _merge_params(*[str(s.get("hardware_params") or "") for s in sigs])
            params = _merge_params(pg, by_type, card_ag)
            modules.append({
                "Station Name": cur["row"].get("profinet_name", "").strip(),
                "Slot": plug, "Module Name": slot, "Model Id": cmodel,
                "I Addr": start, "Q Addr": start,
                "Custom Parameters": params,
                "Comment": crec["comment"] if crec else "",
            })

        # default cards (<PARENT>:SUFFIX) for this device model. Their DTD col-5
        # params are applied by Openn2 itself, so the row carries no params here.
        for card_id in default_cards.get(model.upper(), []):
            crec = by_id[card_id.upper()]
            plug += 1
            modules.append({
                "Station Name": cur["row"].get("profinet_name", "").strip(),
                "Slot": plug, "Module Name": crec["model_id"], "Model Id": crec["model_id"],
                "I Addr": "", "Q Addr": "", "Custom Parameters": "",
                "Comment": crec["comment"],
            })

    for row in io_rows:
        role = _role(row)
        if role is not None:
            finalize()
            model = _model_id(row.get("part_no"))
            rec = by_id.get(model.upper())
            if rec is None:  # device not in DTD -> can't generate; log and skip
                where = f"row {row.get('_source_row')} {row.get('profinet_name') or row.get('device') or ''}".strip()
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


def _format2(rows: list, keys: list) -> str:
    """Comma-delimited format-2 text: '#!format=2' tag, a '# header' comment, then
    one csv-quoted row per dict (fields with ',' or '"' are quoted, as Openn2's
    CsvTable expects). Params inside a field use '|', so they never need quoting."""
    buf = io.StringIO()
    buf.write("#!format=2\n")
    buf.write("# " + ",".join(keys) + "\n")
    writer = csv.writer(buf, lineterminator="\n")  # default delimiter ',', QUOTE_MINIMAL
    for r in rows:
        writer.writerow([str(r.get(k, "")) for k in keys])
    return buf.getvalue()


def write_stations(stations: list, out_dir: str) -> int:
    hw = os.path.join(out_dir, "Hardware")
    os.makedirs(hw, exist_ok=True)
    keys = ["Role", "Station Name", "Model Id", "IP Address", "PN Number", "Subnet", "Custom Parameters", "Group"]
    with open(os.path.join(hw, "Stations.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(_format2(stations, keys))
    return len(stations)


def write_modules(modules: list, out_dir: str) -> int:
    hw = os.path.join(out_dir, "Hardware")
    os.makedirs(hw, exist_ok=True)
    keys = ["Station Name", "Slot", "Module Name", "Model Id", "I Addr", "Q Addr", "Custom Parameters", "Comment"]
    with open(os.path.join(hw, "Modules.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(_format2(modules, keys))
    return len(modules)
