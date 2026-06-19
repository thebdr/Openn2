"""The §6 script-type regex ladder (clean-room port of Pipeline2).

Phase 210 computes the canonical script_type IN CODE - replacing the legacy Excel array formula (so
there is no spill/array-lock hazard). The ladder classifies a row as In/Out/Node by its address
(col G) / id (col F), then matches the bilingual description against an ordered set of patterns and
returns the catalogue type the app writes to AB. The legacy intermediate names (ENC/FA/RES) are
gone - the ladder yields N / Z / R<area> directly, so the AC "Suggested Type" column simply mirrors
what the app would write in script_type.
"""
from __future__ import annotations
import re

from pipeline3.domain.iolist_diag.models import IoRow, INPUT_REQUIRED


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


def suggested_type(row: IoRow) -> str:
    """The §6 ladder: classify the row and return the CANONICAL script_type the app writes to AB
    (encoders -> N, emergency-area outputs -> Z, resets -> R<area>/R*; the legacy ENC/FA/RES
    intermediates are gone). A described-but-unclassifiable row -> <input required>; otherwise ''."""
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
            return "N" + _last(r"CELL.\d", d2) + "/2"
        if _test(desc, r"SWITCH DISCONNECTOR.*OPEN"):
            return "B" + _last(r"CH.", d2) + "/2"
        if _test(desc, r"FIRE ALARM"):
            return "F" + _last(r"CH.", d2) + "/2"
        if _test(desc, r"EMERG.*RESET"):
            area = _last(r"AREA .", d2)
            return f"R{area}" if area.isdigit() else "R*"
        if len(desc) > 3:
            return row.type_hw if row.type_hw.strip() else INPUT_REQUIRED
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
            return "Z" + _last(r"AREA .", d2)
        if len(desc) > 3:
            return INPUT_REQUIRED
        return ""

    if ion == "Node":
        return row.type_hw           # the type_hw column (col R) as-is

    return ""                        # neither I/O nor Node
