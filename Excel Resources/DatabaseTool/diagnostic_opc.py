#!/usr/bin/env python3
"""diagnostic_opc.py - fill the "Diagnostic for OPC" SCL template (NOT the block-CSV path).

Reads the diagnosis rows (the in-diagnosis CentralDatabase rows + rule-generated
>List_Logic entries) and the I/O List `DiagnosticBlocks` sheet, and writes a completed
`Output/Diagnosis/Diagnostic_for_OPC.scl` - one FUNCTION, one REGION per cabinet, each a
CabState call + one BoolToUDInt call per packed DWord (ALARM1/2, WARNING1/2). It also
writes the `List_IO.csv` / `List_Logic.csv` inventories (config-driven columns).

Per channel: IN_xx = the row's PLC binding (outputs.plc_binding), ML_xx = outputs.ml_value,
FL_xx = "PROFINET_ALARMS"."<node profinet_name>_<subnet>". Only assigned channels are
emitted. Alarm vs warning = type_hw (col R) ends with 'W'. diag_bit 0-31 -> DWord 1,
32-63 -> DWord 2; channel = bit % 32. The per-cabinet variant (01-04) comes from
DiagnosticBlocks `TemplateType`; Tristate variants (02/04) pair each alarm DWord with its
warning DWord (the tristate "was-active" output) instead of carrying real warnings.
"""
from __future__ import annotations
import argparse
import csv
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from safetydb import config, staging, outputs
import block_builders
import blockshells
import diagnosis_rules

TEMPLATE = os.path.join(_HERE, "Templates", "Tia Portal Software Blocks",
                        "TEMPLATE--v1.0--06_Diagnostic for OPC.scl")
ALARM_DWORDS = ["ALARM1", "ALARM2"]
WARN_DWORDS = ["WARNING1", "WARNING2"]
DEFAULT_VARIANT = 1


def _is_warning(row) -> bool:
    return str(row.get("type_hw", "")).strip().upper().endswith("W")


def fl_value(db: list, row) -> str:
    """FL_xx mute term: "PROFINET_NODES_ALARM"."<node profinet_name>_<subnet>" of the row's
    node (the node whose I/Q range contains the signal's address); the literal `false`
    (never mute) when no node resolves. A **node-level alarm itself** (PA/PW - it carries
    its own `profinet_name`) must NOT filter on itself, else it would mute the very alarm
    reporting the node down -> `false`."""
    if row.get("profinet_name"):                       # PA/PW: the node-down alarm itself
        return "false"
    node = block_builders.node_of(db, row)
    if node and node.get("profinet_name"):
        return f'"PROFINET_NODES_ALARM"."{node["profinet_name"]}_{node.get("subnet_name", "")}"'
    return "false"


def _entry(db, row, in_binding=None, ml=None) -> dict | None:
    """Normalized diagnosis entry, or None when cabinet/bit are missing/non-numeric."""
    cab, bit = str(row.get("diag_cabinet", "")).strip(), str(row.get("diag_bit", "")).strip()
    if not cab.lstrip("-").isdigit() or not bit.lstrip("-").isdigit():
        return None
    return {
        "cabinet": int(cab), "bit": int(bit), "is_warning": _is_warning(row),
        "in": in_binding if in_binding is not None else outputs.plc_binding(row),
        "ml": ml if ml is not None else outputs.ml_value(row),
        "fl": fl_value(db, row),
    }


def io_entries(db: list) -> list:
    """Diagnosis entries from the in-diagnosis CentralDatabase rows."""
    out = []
    for r in db:
        if (r.get("_type") or {}).get("in_diagnosis"):
            e = _entry(db, r)
            if e:
                out.append(e)
    return out


# --- template parsing ------------------------------------------------------- #
def _parse_template(text: str) -> dict:
    """Split the .scl into reusable pieces: head (up to BEGIN), the REGION line, the
    CabState call, each #Template variant block, the END_REGION line, and the foot."""
    begin = text.index("BEGIN") + len("BEGIN")
    end_fn = text.index("END_FUNCTION")
    head, foot, body = text[:begin], text[end_fn:], text[begin:end_fn]

    region_line = re.search(r"^[ \t]*REGION[^\n]*", body, re.M).group(0)
    end_region_line = re.search(r"^[ \t]*END_REGION[^\n]*", body, re.M).group(0)
    cab = body[body.index('"!!instanceOf:CabState$$"'): body.index("// #Template")].rstrip()
    variants = {int(m.group(1)): m.group(3)
                for m in re.finditer(r"// #Template (\d+)\s*:\s*([^\n]*)\n(.*?)// #Template End",
                                     body, re.S)}
    return {"head": head, "region": region_line, "cabstate": cab,
            "variants": variants, "end_region": end_region_line, "foot": foot}


def _tail_params(block: str) -> list:
    """The non-channel FB params of a variant block (RESET_*, Alarm_Warning_DW, Tristate_DW),
    in order, stripped of indentation / trailing comma / closing `);`."""
    out = []
    for raw in block.splitlines():
        s = raw.strip()
        if not s or s.startswith('"!!instanceOf') or re.match(r"(IN|ML|FL)_\d\d\b", s):
            continue
        s = re.sub(r"\)\s*;?\s*$", "", s).rstrip().rstrip(",").rstrip()
        if s:
            out.append(s)
    return out


def _channels_text(by_ch: dict) -> str:
    lines = []
    for ch in sorted(by_ch):
        e, xx = by_ch[ch], f"{ch:02d}"
        lines.append(f"        IN_{xx} := {e['in']},")
        lines.append(f"        ML_{xx} := {e['ml']},")
        lines.append(f"        FL_{xx} := {e['fl']},")
    return "\n".join(lines)


def _bool_call(inst: str, idx: str, dword: str, alarm_dw: str, warning_dw: str,
               by_ch: dict, tail: list) -> str:
    params = []
    for p in tail:
        p = (p.replace("!!cabinetIndex$$", idx).replace("!!Alarm_Warning_DW$$", dword or alarm_dw)
             .replace("!!Alarm_DW$$", alarm_dw).replace("!!Warning_DW$$", warning_dw))
        params.append(p)
    body = _channels_text(by_ch) + "\n        " + ",\n        ".join(params)
    return f'    "{inst}"(\n{body}\n    );'


def _inst(idx: str, role: str) -> str:
    """FB instance name = the cabinet DWord it backs, e.g. S1.CABINET001.ALARM1 (CabState
    uses .STATE). Quoted by the template's `"!!instanceOf…$$"`."""
    return f"S1.CABINET{idx}.{role}"


def _cabstate(template: str, idx: str) -> str:
    text = (template.replace("!!instanceOf:CabState$$", _inst(idx, "STATE"))
            .replace("!!cabinetIndex$$", idx))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "    " + lines[0] + "".join("\n        " + ln for ln in lines[1:]) if lines else text


def render_scl(db: list, blocks: dict, entries: list) -> str:
    t = _parse_template(open(TEMPLATE, encoding="utf-8-sig").read())
    by_cab = {}
    for e in entries:
        by_cab.setdefault(e["cabinet"], []).append(e)

    regions = []
    for cid in sorted(by_cab):
        blk = blocks.get(cid, {})
        idx = blk.get("index") or f"{cid:03d}"
        tt = int(str(blk.get("template_type") or DEFAULT_VARIANT).strip() or DEFAULT_VARIANT)
        tristate = tt in (2, 4)
        tail = _tail_params(t["variants"].get(tt) or t["variants"][DEFAULT_VARIANT])

        # bucket entries -> {dword: {channel: entry}}
        alarms, warns = {}, {}
        for e in by_cab[cid]:
            fam, dwl = (warns, WARN_DWORDS) if e["is_warning"] else (alarms, ALARM_DWORDS)
            i = 0 if e["bit"] < 32 else 1
            if i < len(dwl):
                fam.setdefault(dwl[i], {})[e["bit"] % 32] = e

        net = blk.get("fld") or f"CABINET {idx}"
        lines = [t["region"].replace("!!NetworkComment$$", net), _cabstate(t["cabstate"], idx)]
        if tristate:                                   # each alarm DWord pairs its warning DWord
            for i, adw in enumerate(ALARM_DWORDS):
                if alarms.get(adw):
                    lines.append(_bool_call(_inst(idx, adw), idx, None, adw, WARN_DWORDS[i],
                                            alarms[adw], tail))
        else:                                          # one call per non-empty DWord
            for dw, chans in list(alarms.items()) + list(warns.items()):
                lines.append(_bool_call(_inst(idx, dw), idx, dw, dw, dw, chans, tail))
        lines.append(t["end_region"])
        regions.append("\n".join(lines))

    return t["head"] + "\n" + "\n\n".join(regions) + "\n" + t["foot"]


# --- generation ------------------------------------------------------------- #
def generate_for(db: list, params: dict, out_dir: str) -> dict:
    """Write List_IO.csv + List_Logic.csv + Diagnostic_for_OPC.scl from an already-staged
    CentralDatabase (so a pipeline run doesn't re-read the I/O List)."""
    blocks = staging.load_diagnostic_blocks(params)
    diag_dir = os.path.join(out_dir, "Diagnosis")
    os.makedirs(diag_dir, exist_ok=True)

    # >List_IO (auto) + >List_Logic (rule-generated) inventories
    io_rows = outputs.build_diagnosis_list_io(db)
    outputs.write_diagnosis_list_io(io_rows, out_dir, "List_IO.csv")
    logic_rows, logic_entries = diagnosis_rules.build_list_logic(db, blocks)
    outputs.write_diagnosis_list_io(logic_rows, out_dir, "List_Logic.csv")

    entries = io_entries(db) + logic_entries
    scl_path = os.path.join(diag_dir, "Diagnostic_for_OPC.scl")
    with open(scl_path, "w", encoding="utf-8-sig", newline="\n") as f:   # BOM, matching the TIA export
        f.write(render_scl(db, blocks, entries))
    return {"io": len(io_rows), "logic": len(logic_rows), "scl": scl_path}


def generate(out_dir: str | None = None, params_path: str | None = None) -> dict:
    params = config.load_params(params_path)
    db, _w = staging.load_io_list(params, config.load_signal_types())
    return generate_for(db, params, out_dir or blockshells._output_dir(params))


def main():
    ap = argparse.ArgumentParser(description="Generate the Diagnostic-for-OPC SCL + List_IO/List_Logic.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    r = generate(args.out)
    print(f"diagnosis: {r['io']} List_IO + {r['logic']} List_Logic  ->  {r['scl']}")


if __name__ == "__main__":
    main()
