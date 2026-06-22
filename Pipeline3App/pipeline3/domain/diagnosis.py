"""Diagnosis Mapping (phase 600): the diagnosis list inventories (610) and the OPC SCL (620).

610 Generate Diag List -> diagnosis_dir/DiagList_IO.csv + DiagList_Logic.csv (config-driven columns
from config_project/diagnosis/diagnosis_columns.csv; each cell is a {canonical} interpolation of the
staged row, the one sentinel column `$PLC_Binding$` -> identity.plc_binding):
  - DiagList_IO  = one row per in-diagnosis staged signal (`_type.in_diagnosis`);
  - DiagList_Logic = rule-generated rows from diagnosis_logic_rules.csv - `required_types` is an OR
    list (the '|' separator), so the rule fires once per row whose script_type is ANY of them, each
    landing at the next free bit of its cabinet's alarm/warning family (per the rule `dev_type`),
    bound to `"<db_name>"."<member>"`.

Clean-room rebuild of Pipeline2's outputs.build_diagnosis_list_io + diagnosis_rules.build_list_logic
(reference for INTENT only). 620 (the OPC SCL fill) reuses `_resolve_logic` and is added next.
"""
from __future__ import annotations
import os
import re

from pipeline3.core import config
from pipeline3.domain import identity, staging
from pipeline3.io import csv_tables

PLC_BINDING_SENTINEL = "$PLC_Binding$"
_LOGIC_RULES_FILE = "diagnosis_logic_rules.csv"

# 620: the OPC diagnosis SCL template (one FUNCTION; one REGION per cabinet).
DIAG_SCL_TEMPLATE = os.path.join(config.BLOCK_TEMPLATES_DIR, "TEMPLATE--v1.0--06_Diagnostic for OPC.scl")
DIAG_SCL_FILE = "Diagnostic_for_OPC.scl"
ALARM_DWORDS = ["ALARM1", "ALARM2"]
WARN_DWORDS = ["WARNING1", "WARNING2"]
DEFAULT_VARIANT = 1


def _is_warning(row) -> bool:
    """A diagnosis row belongs to the WARNING family when its hardware type ends 'W' (an alarm and a
    warning may share a (cabinet,bit) slot - they are different families)."""
    return str(row.get("type_hw", "")).strip().upper().endswith("W")


def _is_warning_devtype(dev_type) -> bool:
    return str(dev_type).strip().upper().endswith("W")


def _diag_cell(expr, row) -> str:
    """One DiagList cell: the `$PLC_Binding$` sentinel -> identity.plc_binding, else the column's
    {canonical} template interpolated against the row."""
    return identity.plc_binding(row) if expr.strip() == PLC_BINDING_SENTINEL else identity.interp(expr, row)


def build_diag_list_io(rows) -> list:
    """One dict per in-diagnosis staged row, keyed by the diagnosis_columns headers."""
    cols = config.load_diagnosis_columns()
    return [{h: _diag_cell(expr, r) for h, expr in cols}
            for r in (rows or []) if (r.get("_type") or {}).get("in_diagnosis")]


def _resolve_logic(rows, blocks, rules) -> list:
    """The rule-generated diagnosis items. `required_types` is an OR list (the '|' separator): a row
    is a match when its script_type is ANY of them, and the rule fires once per matching row (the same
    per-row model as the datablock_elements / interface follower rules). Each match takes the next
    free bit of its cabinet's alarm/warning family (per the rule `dev_type` ending 'W') and binds to
    `"<db_name>"."<member>"`. A matched row's cabinet is its numeric `diag_cabinet`, else a
    paired-channel sibling's cabinet (a row sharing its device FLD that carries one), else FLD ->
    DiagnosisBlocks. Returns [{cabinet, bit, is_warning, binding, src, rule}] - the shared core 610
    (CSV) and 620 (SCL) both build on."""
    fld_to_cab = {b["fld"]: cid for cid, b in (blocks or {}).items() if b.get("fld")}

    # paired-channel co-location: device FLD -> the cabinet of whichever row carrying that FLD has a
    # numeric diag_cabinet, so a matched channel-2 row (no cabinet of its own) lands with its sibling.
    fld_to_cab_sibling: dict = {}
    for r in rows or []:
        dc = str(r.get("diag_cabinet", "")).strip()
        if dc.lstrip("-").isdigit():
            fld_to_cab_sibling.setdefault(identity.fld(r), int(dc))

    # bits already taken per (cabinet, is_warning) by the in-diagnosis rows
    used: dict = {}
    for r in rows or []:
        if not (r.get("_type") or {}).get("in_diagnosis"):
            continue
        cab, bit = str(r.get("diag_cabinet", "")).strip(), str(r.get("diag_bit", "")).strip()
        if cab.lstrip("-").isdigit() and bit.lstrip("-").isdigit():
            used.setdefault((int(cab), _is_warning(r)), set()).add(int(bit))

    def _cabinet_of(r):
        dc = str(r.get("diag_cabinet", "")).strip()
        if dc.lstrip("-").isdigit():
            return int(dc)
        cab = fld_to_cab_sibling.get(identity.fld(r))           # paired-channel sibling
        if cab is None:
            cab = fld_to_cab.get(f"{r.get('functional_unit', '')}{r.get('location', '')}")
        return cab

    items = []
    for rule in rules or []:
        is_warn = _is_warning_devtype(rule["dev_type"])
        for r in rows or []:
            if r.get("script_type") not in rule["required_types"]:   # OR: any required type
                continue
            cab = _cabinet_of(r)
            if cab is None:
                continue
            taken = used.setdefault((cab, is_warn), set())
            bit = 0
            while bit in taken:
                bit += 1
            taken.add(bit)
            db, member = rule["db_name"], identity.interp(rule["member"], r)
            binding = f'"{db}"."{member}"' if db else f'"{member}"'
            items.append({"cabinet": cab, "bit": bit, "is_warning": is_warn,
                          "binding": binding, "src": r, "rule": rule})
    return items


def build_diag_list_logic(rows, blocks, rules=None) -> list:
    """Rule-generated DiagList_Logic rows (dicts keyed by the diagnosis_columns headers). A synthetic
    row carries the rule's assigned diag_cabinet/diag_bit + dev_type/name for the column interpolation,
    plus the rule's diag_desc (when set) for the Diag Desc column; the PLC_Binding column is the rule
    binding."""
    if rules is None:
        rules = config.load_rules(_LOGIC_RULES_FILE, config.DIAGNOSIS_DIR)
    cols = config.load_diagnosis_columns()
    out = []
    for it in _resolve_logic(rows, blocks, rules):
        row = dict(it["src"])
        row["diag_cabinet"], row["diag_bit"] = f"{it['cabinet']:03d}", f"{it['bit']:02d}"
        row["type_hw"] = it["rule"]["dev_type"]
        row["script_type"] = it["rule"]["name"] or it["src"].get("script_type")
        # a rule-supplied diag_desc names the rule-generated diagnosis (e.g. "SAFETY ENCODER FAILURE
        # <FLD>") rather than the source signal's own diag_desc; blank -> keep the source signal's.
        if it["rule"].get("diag_desc"):
            row["diag_desc"] = identity.interp(it["rule"]["diag_desc"], row)
        out.append({h: (it["binding"] if expr.strip() == PLC_BINDING_SENTINEL else identity.interp(expr, row))
                    for h, expr in cols})
    return out


def generate_diag_list(rows, out_root, io_path) -> dict:
    """610 entry: write DiagList_IO.csv + DiagList_Logic.csv to diagnosis_dir (comma CSV). Reads the
    DiagnosisBlocks sheet from io_path for the rule cabinet/FLD mapping.
    Returns {'dir', 'io_count', 'logic_count', 'io_path', 'logic_path'}."""
    blocks = staging.load_diagnostic_blocks(io_path) if io_path and os.path.exists(io_path) else {}
    headers = [h for h, _ in config.load_diagnosis_columns()]
    io_rows = build_diag_list_io(rows)
    logic_rows = build_diag_list_logic(rows, blocks)
    diag_dir = config.out_path(out_root, "diagnosis_dir")
    io_out = csv_tables.write_rows(os.path.join(diag_dir, "DiagList_IO.csv"), headers, io_rows)
    logic_out = csv_tables.write_rows(os.path.join(diag_dir, "DiagList_Logic.csv"), headers, logic_rows)
    return {"dir": diag_dir, "io_count": len(io_rows), "logic_count": len(logic_rows),
            "io_path": io_out, "logic_path": logic_out}


# ============================================================================================== #
# 620 Generate Diag Software Blocks -> blocks_import_dir/Diagnostic_for_OPC.scl
# ============================================================================================== #
# Fill the OPC diagnosis SCL: one FUNCTION, one REGION per cabinet, each a CabState call + one
# BoolToUDInt call per packed DWord (ALARM1/2, WARNING1/2). Per channel IN_xx = the row's PLC binding,
# ML_xx = the mirror-logic value, FL_xx = the node-down mute term. Alarm vs warning = type_hw / dev_type
# ends 'W'; diag_bit 0-31 -> DWord 1, 32-63 -> DWord 2, channel = bit % 32. The per-cabinet variant
# (01-04) comes from the DiagnosisBlocks TemplateType; Tristate variants (02/04) pair each alarm DWord
# with its warning DWord. Clean-room port of Pipeline2's diagnostic_opc.py (reference for INTENT only).


def _addr_byte(bit):
    """('I'|'Q', byte) for an I/Q bit address (I20.0 -> ('I', 20)), else None."""
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def _nodes(rows):
    return [r for r in rows or [] if r.get("profinet_name")]


def node_of(rows, row):
    """The Profinet node whose I/Q byte range contains this signal's address (else None)."""
    ab = _addr_byte(row.get("bit"))
    if not ab:
        return None
    kind, byte = ab
    sk, ek = f"{kind}_startByte", f"{kind}_endByte"
    for n in _nodes(rows):
        s, e = n.get(sk, ""), n.get(ek, "")
        if s != "" and int(s) <= byte <= int(e):
            return n
    return None


def ml_value(row) -> str:
    """ML_xx (mirror logic): the type's diag_logic mirror->TRUE / invert->FALSE; blank -> derived from
    normal_condition (set -> FALSE, empty -> TRUE)."""
    logic = ((row.get("_type") or {}).get("diagnosis_logic") or "").strip().lower()
    if logic == "mirror":
        return "TRUE"
    if logic == "invert":
        return "FALSE"
    nc = str(row.get("normal_condition") or "").strip().lower()
    return "FALSE" if nc and nc not in ("0", "0.0", "false", "no") else "TRUE"


def fl_value(rows, row) -> str:
    """FL_xx mute term: the row's node alarm bit "PROFINET_NODES_ALARM"."<pname> <pip>" (the PA
    db_element shape), or 'false' when no node resolves. A node-level alarm itself (PA/PW, it carries
    its own profinet_name) must NOT filter on itself -> 'false'."""
    if row.get("profinet_name"):
        return "false"
    node = node_of(rows, row)
    if node and node.get("profinet_name"):
        member = f'{node["profinet_name"]} {node.get("profinet_ip", "")}'.strip()
        return f'"PROFINET_NODES_ALARM"."{member}"'
    return "false"


def _entry(rows, *, cabinet, bit, is_warning, in_binding, src):
    return {"cabinet": cabinet, "bit": bit, "is_warning": is_warning,
            "in": in_binding, "ml": ml_value(src), "fl": fl_value(rows, src)}


def diag_entries(rows, blocks, rules) -> list:
    """All SCL channel entries: the in-diagnosis rows + the rule-generated logic items, each as
    {cabinet, bit, is_warning, in, ml, fl}. Rows without a numeric cabinet/bit are dropped."""
    out = []
    for r in rows or []:
        if not (r.get("_type") or {}).get("in_diagnosis"):
            continue
        cab, bit = str(r.get("diag_cabinet", "")).strip(), str(r.get("diag_bit", "")).strip()
        if cab.lstrip("-").isdigit() and bit.lstrip("-").isdigit():
            out.append(_entry(rows, cabinet=int(cab), bit=int(bit), is_warning=_is_warning(r),
                              in_binding=identity.plc_binding(r), src=r))
    for it in _resolve_logic(rows, blocks, rules):
        out.append(_entry(rows, cabinet=it["cabinet"], bit=it["bit"], is_warning=it["is_warning"],
                          in_binding=it["binding"], src=it["src"]))
    return out


# --- SCL template parse + render (faithful to the template's own text) ---------------------- #

def _parse_template(text: str) -> dict:
    """Split the .scl into reusable pieces: head (up to BEGIN), the REGION line, the CabState call,
    each #Template variant block, the END_REGION line, and the foot (from END_FUNCTION)."""
    begin = text.index("BEGIN") + len("BEGIN")
    end_fn = text.index("END_FUNCTION")
    head, foot, body = text[:begin], text[end_fn:], text[begin:end_fn]
    region_line = re.search(r"^[ \t]*REGION[^\n]*", body, re.M).group(0)
    end_region_line = re.search(r"^[ \t]*END_REGION[^\n]*", body, re.M).group(0)
    cab = body[body.index('"!!instanceOf-CabState$$"'): body.index("// #Template")].rstrip()
    variants = {int(m.group(1)): m.group(3)
                for m in re.finditer(r"// #Template (\d+)\s*:\s*([^\n]*)\n(.*?)// #Template End",
                                     body, re.S)}
    return {"head": head, "region": region_line, "cabstate": cab,
            "variants": variants, "end_region": end_region_line, "foot": foot}


def _tail_params(block: str) -> list:
    """The non-channel FB params of a variant block (RESET_*, Alarm_Warning_DW, Tristate_DW), in
    order, stripped of indentation / trailing comma / closing `);`."""
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


def _inst(idx: str, role: str) -> str:
    """FB instance name = the cabinet DWord it backs, e.g. S1.CABINET001.ALARM1 (CabState uses
    .STATE)."""
    return f"S1.CABINET{idx}.{role}"


def _bool_call(inst, idx, dword, alarm_dw, warning_dw, by_ch, tail) -> str:
    params = []
    for p in tail:
        p = (p.replace("!!cabinetIndex$$", idx).replace("!!Alarm_Warning_DW$$", dword or alarm_dw)
             .replace("!!Alarm_DW$$", alarm_dw).replace("!!Warning_DW$$", warning_dw))
        params.append(p)
    body = _channels_text(by_ch) + "\n        " + ",\n        ".join(params)
    return f'    "{inst}"(\n{body}\n    );'


def _cabstate(template: str, idx: str) -> str:
    text = (template.replace("!!instanceOf-CabState$$", _inst(idx, "STATE"))
            .replace("!!cabinetIndex$$", idx))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "    " + lines[0] + "".join("\n        " + ln for ln in lines[1:]) if lines else text


def render_scl(blocks, entries, template_text) -> str:
    t = _parse_template(template_text)
    by_cab: dict = {}
    for e in entries:
        by_cab.setdefault(e["cabinet"], []).append(e)

    regions = []
    for cid in sorted(by_cab):
        blk = (blocks or {}).get(cid, {})
        idx = blk.get("index") or f"{cid:03d}"
        tt = int(str(blk.get("template_type") or DEFAULT_VARIANT).strip() or DEFAULT_VARIANT)
        tristate = tt in (2, 4)
        tail = _tail_params(t["variants"].get(tt) or t["variants"][DEFAULT_VARIANT])

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

    # rename the FUNCTION: drop the TEMPLATE--vX.Y-- prefix (the block-name convention) so the
    # imported block is "06_Diagnostic for OPC", not the template's name.
    head = re.sub(r"TEMPLATE--v[0-9.]+--", "", t["head"], count=1)
    return head + "\n" + "\n\n".join(regions) + "\n" + t["foot"]


def generate_diag_scl(rows, out_root, io_path, *, template_path=None) -> dict:
    """620 entry: fill the OPC diagnosis SCL -> blocks_import_dir/Diagnostic_for_OPC.scl (UTF-8 BOM +
    CRLF, matching the exported template; the FUNCTION is renamed to drop the TEMPLATE--vX.Y-- prefix).
    Returns {'dir', 'path', 'cabinets', 'entries', 'warnings'}. Missing template -> a warning, no file."""
    template_path = template_path or DIAG_SCL_TEMPLATE
    scl_dir = config.out_path(out_root, "blocks_import_dir")
    os.makedirs(scl_dir, exist_ok=True)
    if not os.path.exists(template_path):
        return {"dir": scl_dir, "path": None, "cabinets": 0, "entries": 0,
                "warnings": [f"SCL template not found: {template_path}"]}
    blocks = staging.load_diagnostic_blocks(io_path) if io_path and os.path.exists(io_path) else {}
    rules = config.load_rules(_LOGIC_RULES_FILE, config.DIAGNOSIS_DIR)
    entries = diag_entries(rows, blocks, rules)
    text = render_scl(blocks, entries, open(template_path, encoding="utf-8-sig").read())
    path = os.path.join(scl_dir, DIAG_SCL_FILE)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:   # BOM + CRLF, matching the exported template
        f.write(text)
    cabinets = len({e["cabinet"] for e in entries})
    return {"dir": scl_dir, "path": path, "cabinets": cabinets, "entries": len(entries), "warnings": []}
