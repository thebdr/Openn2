"""Hardware: extract format-2 Stations.csv + Modules.csv from the I/O List.

Roles (per HW for openness v2):
  Script Type (AB) = PLC        -> Plc            (head)
  Script Type (AB) = PlcCardCm  -> PlcCardCm      (head, plugged in the Plc rack)
  Type (R) first letter = P     -> IoDevice       (head, e.g. PN/PN coupler, IM155)
Rows that are not heads are the device's signals; they are grouped into cards by
Slot (col E, the card device tag, e.g. -K65010). Card model = Part No (col C).

Stations columns: Role; Station Name (Profinet name W); Model Id (Part No, no
spaces); IP (V); PN Number (ID, F); Subnet (from IP); Custom Parameters (device
model defaults from the DeviceTypesDatabase); Group (Functional unit O).
Modules columns: Station Name; Slot (plug order); Module Name (card tag E);
Model Id; I Addr; Q Addr (start bytes); Custom Parameters (card model defaults).

Custom-parameter generation logic (PotentialGroup on the first card, default
cards, per-channel overrides) is layered on top later; this builds the
structure + model-default params.
"""
from __future__ import annotations
import os
import re

HEAD_PLC = "PLC"
HEAD_CM = "PLCCARDCM"


def _model_id(part_no) -> str:
    return str(part_no or "").replace(" ", "").strip()


def _subnet(ip: str) -> str:
    parts = str(ip or "").split(".")
    return f"Subnet{parts[2]}" if len(parts) == 4 else ""


def _role(row) -> str | None:
    script = str(row.get("script_type") or "").strip().upper()
    if script == HEAD_PLC:
        return "Plc"
    if script == HEAD_CM:
        return "PlcCardCm"
    if str(row.get("type_hw") or "").strip()[:1].upper() == "P":
        return "IoDevice"
    return None


_ADDR = re.compile(r"\s*([IQ])\s*(\d+)\.(\d+)", re.IGNORECASE)


def parse_address(value):
    """'I0.0' -> ('I', 0, 0); 'Q12.3' -> ('Q', 12, 3); else None."""
    m = _ADDR.match(str(value or ""))
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), int(m.group(3))


def extract_stations(io_rows: list, dtd: dict) -> list:
    stations = []
    for row in io_rows:
        role = _role(row)
        if role is None:
            continue
        model = _model_id(row.get("part_no"))
        dev = dtd.get(model.upper())
        stations.append({
            "Role": role,
            "Station Name": str(row.get("profinet_name") or "").strip(),
            "Model Id": model,
            "IP Address": str(row.get("profinet_ip") or "").strip(),
            "PN Number": str(row.get("id_node") or "").strip(),
            "Subnet": _subnet(row.get("profinet_ip")),
            "Custom Parameters": dev["params"] if dev else "",
            "Group": str(row.get("functional_unit") or "").strip(),
            "_source_row": row.get("_source_row"),
        })
    return stations


def extract_modules(io_rows: list, dtd: dict) -> list:
    """Walk rows in order; under each IoDevice head, group signal rows into cards
    by Slot (E). I/Q Addr = the card's lowest input/output start byte."""
    modules = []
    current_station = None
    plug_order = 0
    card = None  # accumulator for the current Slot group

    def flush(c):
        if not c:
            return
        i_bytes = [b for (t, b) in c["addrs"] if t == "I"]
        q_bytes = [b for (t, b) in c["addrs"] if t == "Q"]
        dev = dtd.get(c["model"].upper())
        modules.append({
            "Station Name": c["station"],
            "Slot": c["slot_order"],
            "Module Name": c["name"],
            "Model Id": c["model"],
            "I Addr": min(i_bytes) if i_bytes else "",
            "Q Addr": min(q_bytes) if q_bytes else "",
            "Custom Parameters": dev["params"] if dev else "",
        })

    for row in io_rows:
        if _role(row) is not None:  # a head row: start a new station context
            flush(card)
            card = None
            current_station = str(row.get("profinet_name") or "").strip()
            plug_order = 0
            continue
        if current_station is None:
            continue
        slot_tag = str(row.get("slot") or "").strip()  # card device tag (col E)
        if not slot_tag:
            continue
        if card is None or card["name"] != slot_tag:
            flush(card)
            plug_order += 1
            card = {"station": current_station, "name": slot_tag,
                    "model": _model_id(row.get("part_no")), "slot_order": plug_order,
                    "addrs": []}
        addr = parse_address(row.get("bit"))
        if addr:
            card["addrs"].append((addr[0], addr[1]))
    flush(card)
    return modules


def _format2(headers: list, comment: str, rows: list, key_order: list) -> str:
    out = ["#!format=2", "# " + comment]
    for r in rows:
        out.append(";".join(str(r.get(k, "")) for k in key_order))
    return "\n".join(out) + "\n"


def write_stations(stations: list, out_dir: str) -> int:
    hw_dir = os.path.join(out_dir, "Hardware")
    os.makedirs(hw_dir, exist_ok=True)
    keys = ["Role", "Station Name", "Model Id", "IP Address", "PN Number", "Subnet", "Custom Parameters", "Group"]
    text = _format2(keys, ";".join(keys), stations, keys)
    with open(os.path.join(hw_dir, "Stations.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    return len(stations)


def write_modules(modules: list, out_dir: str) -> int:
    hw_dir = os.path.join(out_dir, "Hardware")
    os.makedirs(hw_dir, exist_ok=True)
    keys = ["Station Name", "Slot", "Module Name", "Model Id", "I Addr", "Q Addr", "Custom Parameters"]
    text = _format2(keys, ";".join(keys), modules, keys)
    with open(os.path.join(hw_dir, "Modules.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    return len(modules)
