#!/usr/bin/env python3
"""diagnosis_rules.py - rule-generated >List_Logic entries.

`config/diagnosis_logic_rules.csv` rules each fire when ALL their `required_types`
(`|`-separated script_types) are present **within one cabinet** (the matched rows' FLD ->
DiagnosticBlocks). The generated entry lands at the **next free bit** of that cabinet's
alarm/warning family (per `dev_type`), with IN binding `"<db_name>"."<member>"` (or just
`"<member>"` when `db_name` is empty); `member` interpolates CentralDatabase `{columns}`
of a representative matched row. Returns the List_Logic CSV rows + the SCL channel entries.
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config, outputs


def _is_warning_devtype(dev_type: str) -> bool:
    return str(dev_type).strip().upper().endswith("W")


def load_rules() -> list:
    """[{name, required_types:[...], dev_type, db_name, member}] from the rules CSV ({} if absent)."""
    path = os.path.join(config.CONFIG_DIR, "diagnosis_logic_rules.csv")
    if not os.path.exists(path):
        return []
    rules = []
    for r in config._read_csv("diagnosis_logic_rules.csv"):
        req = [t.strip() for t in (r.get("required_types") or "").split("|") if t.strip()]
        if not req:
            continue
        rules.append({
            "name": (r.get("name") or "").strip(),
            "required_types": req,
            "dev_type": (r.get("dev_type") or "A").strip(),
            "db_name": (r.get("db_name") or "").strip(),
            "member": (r.get("member") or "").strip(),
        })
    return rules


def _binding(rule: dict, src_row: dict) -> str:
    member = outputs._resolve_tokens(rule["member"], src_row).strip()
    db = rule["db_name"]
    return f'"{db}"."{member}"' if db else f'"{member}"'


def build_list_logic(db: list, blocks: dict) -> tuple[list, list]:
    """(list_logic_rows, scl_entries). `blocks` = staging.load_diagnostic_blocks()."""
    from diagnostic_opc import fl_value, _is_warning  # lazy: avoid an import cycle
    rules = load_rules()
    cols = config.load_diagnosis_columns()
    fld_to_cab = {b["fld"]: cid for cid, b in blocks.items() if b.get("fld")}

    # bits already taken per (cabinet, is_warning) by the in-diagnosis rows
    used = {}
    for r in db:
        if not (r.get("_type") or {}).get("in_diagnosis"):
            continue
        cab, bit = str(r.get("diag_cabinet", "")).strip(), str(r.get("diag_bit", "")).strip()
        if cab.isdigit() and bit.lstrip("-").isdigit():
            used.setdefault((int(cab), _is_warning(r)), set()).add(int(bit))

    logic_rows, entries = [], []
    for rule in rules:
        # group matched rows by cabinet (FLD -> DiagnosticBlocks; fallback the row's diag_cabinet)
        by_cab = {}
        for r in db:
            if r.get("script_type") not in rule["required_types"]:
                continue
            fld = f"{r.get('functional_unit', '')}{r.get('location', '')}"
            cab = fld_to_cab.get(fld)
            if cab is None and str(r.get("diag_cabinet", "")).strip().isdigit():
                cab = int(r.get("diag_cabinet"))
            if cab is not None:
                by_cab.setdefault(cab, {}).setdefault(r["script_type"], []).append(r)

        is_warn = _is_warning_devtype(rule["dev_type"])
        for cab, present in sorted(by_cab.items()):
            if not all(t in present for t in rule["required_types"]):
                continue
            taken = used.setdefault((cab, is_warn), set())
            bit = 0
            while bit in taken:
                bit += 1
            taken.add(bit)
            src = present[rule["required_types"][0]][0]
            binding = _binding(rule, src)

            row = dict(src)            # synthetic row for column interpolation
            row["diag_cabinet"], row["diag_bit"] = f"{cab:03d}", f"{bit:02d}"
            row["type_hw"], row["script_type"] = rule["dev_type"], rule["name"] or src.get("script_type")
            logic_rows.append({h: (binding if expr.strip() == outputs.PLC_BINDING_SENTINEL
                                   else outputs._resolve_tokens(expr, row).strip())
                               for h, expr in cols})
            entries.append({"cabinet": cab, "bit": bit, "is_warning": is_warn,
                            "in": binding, "ml": outputs.ml_value(src), "fl": fl_value(db, src)})
    return logic_rows, entries
