"""The §6 suggested-type regex ladder + to_canonical (clean-room port of Pipeline2).

Phase 210 computes the suggested type (legacy names, written to AC) and the canonical script_type
(written to AB) IN CODE - replacing the legacy Excel array formula (so there is no spill/array-lock
hazard). The ladder classifies a row as In/Out/Node by its address (col G) / id (col F), then matches
the bilingual description against an ordered set of patterns.
"""
from __future__ import annotations
import re

from pipeline3.domain.iolist_diag.models import IoRow, INPUT_REQUIRED, SUGGEST_UNMATCHED


def _clean(s) -> str:
    s = re.sub(r"[\x00-\x1f]", " ", str(s if s is not None else ""))
    return re.sub(r"\s+", " ", s).strip()


def _test(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text or "", re.IGNORECASE))


def _last(pattern: str, text: str) -> str:
    """Last character of the first match of `pattern` in `text` (case-insensitive), else ''."""
    m = re.search(pattern, text or "", re.IGNORECASE)
    return m.group(0)[-1] if m else ""


def in_out_node(row: IoRow) -> str:
    """Classify the row by its I/O address (col G) / node id (col F): In / Out / Node / ''."""
    addr = row.addr or ""
    if "i" in addr.lower():
        return "In"
    if _test(addr, r"O|Q"):
        return "Out"
    try:
        if float(row.id_node) > 0:
            return "Node"
    except (TypeError, ValueError):
        pass
    return ""


def suggested_type(row: IoRow):
    """The §6 ladder. Returns a legacy type string, '???', '' or False (the formula's dangling IF)."""
    d1 = _clean(row.desc_l1)
    d2 = _clean(row.desc_l1b)
    desc = f"{d1} {d2}".strip()
    ion = in_out_node(row)

    if ion == "In":
        if _test(desc, r"EMERGENCY PUSH.BUTTON PRES"):
            return "E" + _last(r"CH.", d2) + "/2"
        if _test(desc, r"FEEDBACK.*SAFE.*(RELAY|CONTACTOR)"):
            return "KI"
        if _test(desc, r"DOOR.*OPEN"):
            if _test(d2, r"CH"):
                return "DI" + _last(r"CH.", d2) + "/2"
            if _test(d2, r"RESET"):
                return "DR"
            return "DD"
        if _test(desc, r"SAFETY ENCODER.*PHOTO"):
            return "ENC" + _last(r"CELL.\d", d2) + "/2"
        if _test(desc, r"SWITCH DISCONNECTOR.*OPEN"):
            return "B" + _last(r"CH.", d2) + "/2"
        if _test(desc, r"FIRE ALARM"):
            return "F" + _last(r"CH.", d2) + "/2"
        if _test(desc, r"EMERG.*RESET"):
            return "RES"
        if len(desc) > 3:
            return row.type_hw if row.type_hw.strip() else SUGGEST_UNMATCHED
        return ""

    if ion == "Out":
        if _test(d1, r"(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)"):
            return "KQ"
        if _test(d1, r"DOOR.*OPEN$|SOLENOID.*CONTROL"):
            return "DQ"
        if _test(d2, r"(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)"):
            return "KQ"
        if _test(desc, r"DOOR.*LAMP"):
            return "DL"
        if _test(d2, r"EMERGENCY AREA \d"):
            return "FA" + _last(r"AREA .", d2)
        if len(desc) > 3:
            return SUGGEST_UNMATCHED
        return ""

    if ion == "Node":
        return row.type_hw           # the type_hw column (col R) as-is

    return False                     # neither I/O nor Node


def to_canonical(suggested, row: IoRow) -> str:
    """Map a legacy suggested type to the catalogue: ENC->N, FA->Z, RES->R<area>/R*; '???' surfaces
    as <input required>; everything else passes through."""
    if suggested is False or suggested == "":
        return ""
    s = str(suggested)
    if s == SUGGEST_UNMATCHED:
        return INPUT_REQUIRED
    up = s.upper()
    if up.startswith("ENC"):
        return "N" + s[3:]
    if up.startswith("FA"):
        return "Z" + s[2:]
    if up == "RES":
        area = _last(r"AREA .", _clean(row.desc_l1b))
        return f"R{area}" if area.isdigit() else "R*"
    return s
