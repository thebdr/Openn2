"""Phase 620 - project the unified `diagnosis_entries` + `diagnosis_cabinets` to the OPC diagnosis SCL
(`Diagnostic_for_OPC.scl`, the OP4 BuilderData surface).

Fills the `06_Diagnostic for OPC.scl` template: one FUNCTION, one REGION per cabinet, each a CabState call
+ one BoolToUDInt call per packed DWord (ALARM1/2, WARNING1/2). Per channel IN_xx/ML_xx/FL_xx come from the
entry's STORED `in_binding`/`ml_value`/`fl_value` (computed at 600b - so this projector is pure text). bit
0-31 -> DWord 1, 32-63 -> DWord 2, channel = bit % 32. The cabinet variant (01-04) is the
`diagnosis_cabinets.template_type`; TRISTATE (pair each alarm DWord with its warning DWord) is enabled when
the template_type is 02/04 OR the cabinet contains a signal whose type has `tristate=yes` (the user's
per-type flag - an additional trigger). UTF-8 BOM + CRLF; the FUNCTION is renamed to drop the
`TEMPLATE--vX.Y--` prefix. Clean-room port of PL3's diagnosis.py SCL section.
"""
from __future__ import annotations

import os
import re

from pipeline4.core import config
from pipeline4.core.database import Database
from pipeline4.core.finding import Finding
from pipeline4.domain.diagnosis import _int_or_none
from pipeline4.domain.diagnosis_entries import diagnosis_cabinets_table, diagnosis_entries_table
from pipeline4.domain.signals import signals_table


def _f(type: str, severity: str, detail: str, location: str = "") -> Finding:
    """A phase-620 Finding - the OPC-SCL projection report container (WARN-only: the SCL template absent)."""
    return Finding(phase=620, type=type, severity=severity, detail=detail, location=location)


DIAG_SCL_FILE = "Diagnostic_for_OPC.scl"
ALARM_DWORDS = ["ALARM1", "ALARM2"]
WARN_DWORDS = ["WARNING1", "WARNING2"]
DEFAULT_VARIANT = 1


# --- SCL template parse + render (faithful to the template's own text) -------------------------- #
def _parse_template(text: str) -> dict:
    """Split the .scl into reusable pieces: head (up to BEGIN), the REGION line, the CabState call, each
    #Template variant block, the END_REGION line, and the foot (from END_FUNCTION)."""
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
    """The non-channel FB params of a variant block (RESET_*, Alarm_Warning_DW, Tristate_DW), in order,
    stripped of indentation / trailing comma / closing `);`."""
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
    """FB instance name = the cabinet DWord it backs, e.g. S1.CABINET001.ALARM1 (CabState uses .STATE)."""
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


def render_scl(blocks, entries, template_text, tristate_cabinets=()) -> str:
    """Render the SCL from `blocks` (cabinet_id -> {index, template_type, fld}), `entries`
    ({cabinet, bit, is_warning, in, ml, fl}), and the set of `tristate_cabinets` (cabinet ids whose
    template_type says tristate OR which contain a tristate-type signal)."""
    t = _parse_template(template_text)
    tri_set = set(tristate_cabinets)
    by_cab: dict = {}
    for e in entries:
        by_cab.setdefault(e["cabinet"], []).append(e)

    regions = []
    for cid in sorted(by_cab):
        blk = (blocks or {}).get(cid, {})
        idx = blk.get("index") or f"{cid:03d}"
        tt = int(str(blk.get("template_type") or DEFAULT_VARIANT).strip() or DEFAULT_VARIANT)
        tristate = tt in (2, 4) or cid in tri_set          # template_type OR a per-type tristate signal
        # the tail params come from the tristate VARIANT: if a per-type flag forces tristate on an odd
        # (non-tristate) template_type, use its tristate counterpart (1->2, 3->4) so the call has the
        # Tristate_DW param. In the real data the trigger only fires where tt is already 2 (a no-op).
        variant = tt + 1 if (tristate and tt % 2 == 1) else tt
        tail = _tail_params(t["variants"].get(variant) or t["variants"][DEFAULT_VARIANT])

        alarms, warns = {}, {}
        for e in by_cab[cid]:
            fam, dwl = (warns, WARN_DWORDS) if e["is_warning"] else (alarms, ALARM_DWORDS)
            i = 0 if e["bit"] < 32 else 1
            if i < len(dwl):
                fam.setdefault(dwl[i], {})[e["bit"] % 32] = e

        net = blk.get("fld") or f"CABINET {idx}"
        lines = [t["region"].replace("!!NetworkComment$$", net), _cabstate(t["cabstate"], idx)]
        if tristate:                                       # each alarm DWord pairs its warning DWord
            for i, adw in enumerate(ALARM_DWORDS):
                if alarms.get(adw):
                    lines.append(_bool_call(_inst(idx, adw), idx, None, adw, WARN_DWORDS[i],
                                            alarms[adw], tail))
        else:                                              # one call per non-empty DWord
            for dw, chans in list(alarms.items()) + list(warns.items()):
                lines.append(_bool_call(_inst(idx, dw), idx, dw, dw, dw, chans, tail))
        lines.append(t["end_region"])
        regions.append("\n".join(lines))

    # rename the FUNCTION: drop the TEMPLATE--vX.Y-- prefix so the imported block is "06_Diagnostic for OPC".
    head = re.sub(r"TEMPLATE--v[0-9.]+--", "", t["head"], count=1)
    return head + "\n" + "\n\n".join(regions) + "\n" + t["foot"]


def _tristate_cabinets(database) -> set:
    """Cabinet ids that contain a signal whose type has `tristate=yes` (the user's per-type trigger)."""
    out = set()
    for r in database["signals"] if "signals" in database else []:
        if (r.get("type") or {}).get("tristate"):
            cid = _int_or_none(r.get("diag_cabinet"))
            if cid is not None:
                out.add(cid)
    return out


def _scl_entries(database) -> list:
    """The SCL channel entries from `diagnosis_entries`: only rows with a numeric (cabinet, bit) - matching
    PL3's `diag_entries` (an in-diag signal with no numeric cabinet/bit is on the DiagList but not the SCL)."""
    out = []
    for e in database["diagnosis_entries"]:
        cab, bit = _int_or_none(e.get("cabinet")), _int_or_none(e.get("bit"))
        if cab is None or bit is None:
            continue
        out.append({"cabinet": cab, "bit": bit, "is_warning": bool(e.get("is_warning")),
                    "in": e.get("in_binding", ""), "ml": e.get("ml_value", ""), "fl": e.get("fl_value", "")})
    return out


def _blocks(database) -> dict:
    out = {}
    for c in database["diagnosis_cabinets"] if "diagnosis_cabinets" in database else []:
        cid = _int_or_none(c.get("cabinet_id"))
        if cid is not None:
            out[cid] = {"index": c.get("index", ""), "template_type": c.get("template_type", ""),
                        "fld": c.get("fld", "")}
    return out


def project(database: Database | None = None, out_dir: str | None = None,
            template_path: str | None = None) -> dict:
    """Write Diagnostic_for_OPC.scl (UTF-8 BOM + CRLF) from `diagnosis_entries` + `diagnosis_cabinets` +
    the signals' per-type tristate flag. Returns {'dir', 'path', 'cabinets', 'entries', 'findings'};
    a missing template -> the `diag_scl_template_missing` WARN, no file (a pure projection - no record)."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = Database([signals_table([m["canonical"] for m in colmap]),
                             diagnosis_cabinets_table(), diagnosis_entries_table()]).load(config.database_dir())
    template_path = template_path or config.DIAG_SCL_TEMPLATE
    out_dir = out_dir or config.blocks_import_dir()
    os.makedirs(out_dir, exist_ok=True)
    if not os.path.exists(template_path):
        return {"dir": out_dir, "path": None, "cabinets": 0, "entries": 0,
                "findings": [_f("diag_scl_template_missing", "WARN",
                                f"SCL template not found: {template_path}", template_path)]}
    entries = _scl_entries(database)
    text = render_scl(_blocks(database), entries, open(template_path, encoding="utf-8-sig").read(),
                      _tristate_cabinets(database))
    path = os.path.join(out_dir, DIAG_SCL_FILE)
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:    # BOM + CRLF (the exported-template format)
        fh.write(text)
    return {"dir": out_dir, "path": path, "cabinets": len({e["cabinet"] for e in entries}),
            "entries": len(entries), "findings": []}
