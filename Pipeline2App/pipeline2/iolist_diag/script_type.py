"""Task A - script_type (AB) by porting the suggested-type formula (spec §6).

`suggested_type(row)` is a faithful Python port of the workbook's AC array formula (the
EMERGENCY-PB / FEEDBACK / DOOR / ENCODER / SWITCH-DISCONNECTOR / RESET regex ladder, with
In/Out/Node detection from the I/O address). It returns exactly what AC holds - including the
formula's quirks: a Node row -> its `type_hw`; an In/Out row that "looks real" but matches no
rule -> the `???` sentinel (or `type_hw`); a row that classifies as none of In/Out/Node ->
boolean `False` (the formula's dangling IF). It emits the LEGACY names (ENC/RES/FA#).

`to_canonical(suggested, row)` maps that to the catalogue's canonical script_type (ENC#->N#,
FA#->Z#, RES->R* or R<area>) and surfaces the `???` sentinel as the `<input required>` marker.
"""
from __future__ import annotations
import re

from pipeline2.iolist_diag.models import INPUT_REQUIRED, SUGGEST_UNMATCHED, IoRow

_IC = re.IGNORECASE   # Excel REGEXTEST/REGEXEXTRACT flag 1 = case-insensitive


def _clean(s: str) -> str:
    """TRIM(CLEAN(...)): drop control chars, collapse whitespace runs, strip."""
    return " ".join((s or "").split())


def _test(pattern: str, text: str) -> bool:
    return re.search(pattern, text or "", _IC) is not None


def _last(pattern: str, text: str) -> str:
    """RIGHT(REGEXEXTRACT(text, pattern), 1): last char of the matched substring ('' if none)."""
    m = re.search(pattern, text or "", _IC)
    return m.group(0)[-1:] if m else ""


def in_out_node(row: IoRow) -> str:
    """'In' | 'Out' | 'Node' | '' from the I/O address (col G) then the node id (col F)."""
    addr = row.addr
    if "i" in addr.lower():                       # SEARCH("i", IoAddr)
        return "In"
    if re.search("O|Q", addr, _IC):               # REGEXTEST(IoAddr, "O|Q")
        return "Out"
    try:
        if float(row.id_node) > 0:                # getNodeId(r) > 0
            return "Node"
    except (TypeError, ValueError):
        pass
    return ""


def suggested_type(row: IoRow):
    """Port of the AC array formula. Returns str | bool (False for the unclassified case)."""
    d1, d2 = _clean(row.desc_l1), _clean(row.desc_l1b)
    desc = f"{d1} {d2}".strip()
    ion = in_out_node(row)

    if ion == "In":
        if _test(r"EMERGENCY PUSH.BUTTON PRES", desc):
            return "E" + _last(r"CH.", d2) + "/2"
        if _test(r"FEEDBACK.*SAFE.*(RELAY|CONTACTOR)", desc):
            return "KI"
        if _test(r"DOOR.*OPEN", desc):
            if _test(r"CH", d2):
                return "DI" + _last(r"CH.", d2) + "/2"
            if _test(r"RESET", d2):
                return "DR"
            return "DD"
        if _test(r"SAFETY ENCODER.*PHOTO", desc):
            return "ENC" + _last(r"CELL.\d", d2) + "/2"
        if _test(r"SWITCH DISCONNECTOR.*OPEN", desc):
            return "B" + _last(r"CH.", d2) + "/2"
        if _test(r"EMERG.*RESET", desc):
            return "RES"
        if len(desc) > 3:
            return row.type_hw if row.type_hw.strip() else SUGGEST_UNMATCHED
        return ""

    if ion == "Out":
        if _test(r"(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)", d1):
            return "KQ"
        if _test(r"DOOR.*OPEN$|SOLENOID.*CONTROL", d1):
            return "DQ"
        if _test(r"(SAFE.*(RELAY|CONTACTOR)|CUT.OFF.*AREA)", d2):
            return "KQ"
        if _test(r"DOOR.*LAMP", desc):
            return "DL"
        if _test(r"EMERGENCY AREA \d", d2):
            return "FA" + _last(r"AREA .", d2)
        if len(desc) > 3:
            return SUGGEST_UNMATCHED
        return ""

    if ion == "Node":
        return row.type_hw                         # TEXT(getIoType(r), "")

    return False                                    # the formula's dangling IF -> FALSE


def to_canonical(suggested, row: IoRow) -> str:
    """The catalogue's canonical script_type for an AC value (spec §7.1 old->new map):
    ENC#->N#, FA#->Z#, RES->R* (or R<area> when the description names an area); the `???`
    sentinel surfaces as the `<input required>` marker; a non-signal ('' / False) -> ''."""
    if suggested is False or suggested == "":
        return ""
    s = str(suggested)
    if s == SUGGEST_UNMATCHED:
        return INPUT_REQUIRED
    up = s.upper()
    if up.startswith("ENC"):
        return "N" + s[3:]                          # ENC1/2 -> N1/2
    if up.startswith("FA"):
        return "Z" + s[2:]                          # FA1 -> Z1
    if up == "RES":
        area = _last(r"AREA .", _clean(row.desc_l1b))
        return f"R{area}" if area.isdigit() else "R*"
    return s
