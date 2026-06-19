"""§8 DIAGNOSIS allocation (columns AE diag_cabinet + AF diag_bit) and the ordered DiagBlock list.

Only in_diag rows get a cabinet/bit. Rows split into node-based (no family / family with no Type-2
diag_block: A/W/KQ/PA/PW) -> physical node cabinets (Type-1), and family-based (family.diag_block
set: doors/encoders/breakers/fire/emergency PB/areas) -> generated Type-2 blocks. A lone PA/PW on a
node is inferred into the shared +FieldIODevices block. Node cabinets: non-P bits grow UP from
diag_bit_min, P bits grow DOWN from diag_bit_max. Type-2 family blocks grow UP; +FieldIODevices DOWN.
Clean-room port of Pipeline2.
"""
from __future__ import annotations
from collections import defaultdict

from pipeline3.domain.iolist_diag.models import DiagBlock, td_in_diag, td_is_p

_FIELD = "+FieldIODevices"
_TYPE2_ORDER = [
    _FIELD, "+SafetyDoors", "+SafetyEncoders", "+SafetyBreakers",
    "+FireAlarm", "+EmergencyPushButtons", "+EmergencyAreas",
]


def _family_offset(r) -> int:
    """0-based bit offset within a Type-2 family block."""
    idx = int(r.index)
    key = r.family.key.upper()
    if key == "N":                               # encoder: two channels per index
        return (idx - 1) * 2 + (0 if r.type_def.get("channel") == "1" else 1)
    if key == "D":                               # door: DI at base+1, DD at base+2 (bit 0 reserved per pair)
        base = (idx - 1) * 2
        return base + 1 if (r.script_type or "").upper().startswith("DI") else base + 2
    if key == "Z":                               # emergency area: bit = the area number
        digits = "".join(c for c in (r.script_type or "") if c.isdigit())
        return int(digits) if digits else 0
    return idx - 1                               # E / B / F: one bit per object


def allocate(results: list, params: dict) -> list:
    min_b = int(params.get("diag_bit_min", 0) or 0)
    max_b = int(params.get("diag_bit_max", 62) or 62)
    cap = max_b - min_b + 1

    diag = [r for r in results if r.type_def and td_in_diag(r.type_def) and not r.skipped]
    node_based = [r for r in diag if not (r.family and r.family.diag_block)]
    fam_based = [r for r in diag if r.family and r.family.diag_block and str(r.index).isdigit()]
    project_fu = next((r.iorow.functional_unit for r in diag if r.iorow.functional_unit), "")

    # --- field inference: a lone PA/PW on a node -> +FieldIODevices instead of a dedicated cabinet --- #
    by_fl = defaultdict(list)
    for r in node_based:
        by_fl[r.iorow.node_fl].append(r)
    node_fls, field_rows, seen = [], [], set()
    for r in node_based:
        fl = r.iorow.node_fl
        if fl in seen:
            continue
        seen.add(fl)
        rs = by_fl[fl]
        if len(rs) == 1 and td_is_p(rs[0].type_def):
            field_rows.append(rs[0])
        else:
            node_fls.append(fl)

    blocks, node_id, type2_id, idc = [], {}, {}, 0

    # Type-1 node cabinets first (node_fl row order)
    for fl in node_fls:
        rep = by_fl[fl][0].iorow
        blocks.append(DiagBlock(id_local=idc, fu=rep.functional_unit, location=rep.location,
                                full_name=rep.functional_unit + rep.location, template_type=1))
        node_id[fl] = idc
        idc += 1

    # Type-2 generated blocks: +FieldIODevices, then canonical family order, then any extras
    by_block = defaultdict(list)
    for r in fam_based:
        by_block[r.family.diag_block].append(r)
    stems = [s for s in _TYPE2_ORDER if (s == _FIELD and field_rows) or s in by_block]
    stems += [s for s in by_block if s not in _TYPE2_ORDER]

    for stem in stems:
        if stem == _FIELD:
            n_inst = (len(field_rows) - 1) // cap + 1 if field_rows else 0
        else:
            max_off = max(_family_offset(r) for r in by_block[stem])
            n_inst = max_off // cap + 1
        for inst in range(1, n_inst + 1):
            loc = f"{stem}_{inst}"
            blocks.append(DiagBlock(id_local=idc, fu=project_fu, location=loc,
                                    full_name=project_fu + loc, template_type=2,
                                    family=stem, instance=inst))
            type2_id[(stem, inst)] = idc
            idc += 1

    # --- bit allocation --- #
    nonp = {fl: min_b for fl in node_fls}
    pdown = {fl: max_b for fl in node_fls}
    for r in sorted(node_based, key=lambda r: (r.iorow.sheet, r.iorow.row)):
        fl = r.iorow.node_fl
        if fl not in node_id:                    # a field row - allocated below
            continue
        if td_is_p(r.type_def):
            bit = pdown[fl]; pdown[fl] -= 1
        else:
            bit = nonp[fl]; nonp[fl] += 1
        r.diag_cabinet = f"{node_id[fl]:03d}"
        r.diag_bit = f"{bit:02d}"

    for i, r in enumerate(field_rows):
        cid = type2_id[(_FIELD, i // cap + 1)]
        r.diag_cabinet = f"{cid:03d}"
        r.diag_bit = f"{max_b - (i % cap):02d}"

    for r in fam_based:
        p = _family_offset(r)
        cid = type2_id[(r.family.diag_block, p // cap + 1)]
        r.diag_cabinet = f"{cid:03d}"
        r.diag_bit = f"{min_b + (p % cap):02d}"

    return blocks
