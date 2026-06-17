"""Task C - diag_cabinet (AE) + diag_bit (AF) and the diagnosis-block set (spec §8).

Only rows whose type has in_diag != no get a bit. A signal maps to a cabinet:
  - object families with a destination block (door/encoder/E/B/F/Z) -> a Type-2 generated block
    (+SafetyDoors_n, +SafetyEncoders_n, +EmergencyPushButtons_n, +SafetyBreakers_n, +FireAlarm_n,
    +EmergencyAreas_n); their per-object bit layout is verified against the golden (below);
  - everything else (A/W/KQ, and PA/PW) is node-based: it lands in the physical-node cabinet
    (Type-1, FullName = FU+location). A lone PA/PW on a node that needs only ONE diag bit is moved
    to the shared +FieldIODevices_n instead of a wasteful one-bit cabinet (the §8 Field inference).

Bit layout: in a node cabinet the P-types (PA/PW) fill from diag_bit_max DOWN and every other
signal from diag_bit_min UP (row order) - they grow toward each other. Type-2 blocks fill per
family with capacity rollover into the next numbered instance. `allocate` mutates each row's
diag_cabinet/diag_bit and returns the ordered DiagBlock list (Type-1 first, then Type-2).
"""
from __future__ import annotations
from collections import defaultdict

from pipeline2.iolist_diag.models import BlockKind, DiagBlock, RowResult

# Emit order for the generated (Type-2) blocks - their ID_Local continues after the node range.
# (Matches the golden's generated-block ordering; IDs are derived, so order is cosmetic - the join
# is AE -> block by ID, and the acceptance compares through FullName, not the absolute ID.)
_TYPE2_ORDER = [
    "+FieldIODevices", "+SafetyDoors", "+SafetyEncoders", "+SafetyBreakers",
    "+FireAlarm", "+EmergencyPushButtons", "+EmergencyAreas",
]
_FIELD = "+FieldIODevices"


def _common_fu(rows: list[RowResult]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.iorow.functional_unit] += 1
    return max(counts, key=counts.get) if counts else ""


def _family_offset(r: RowResult) -> int:
    """The 0-based bit offset `p` of a Type-2 family row within its block's bit space (verified vs
    the golden). EmergencyPushButtons/Breakers/FireAlarm: index-1. Encoder (stride 2): photocell
    1/2 = (index-1)*2 (+0/+1). Doors (stride 2, bit 0 reserved): DI1/2 = 2*index-1, DD = 2*index.
    EmergencyAreas: the area number parsed from Z<n> (bit 0 reserved)."""
    idx = int(r.index)
    key = r.family.key.upper()
    if key == "N":                                   # encoder
        return (idx - 1) * 2 + (0 if r.type_def.channel == "1" else 1)
    if key == "D":                                   # door: DI1/2 then DD (bit 0 reserved)
        base = (idx - 1) * 2
        return base + 1 if r.script_type.upper().startswith("DI") else base + 2
    if key == "Z":                                   # emergency area: bit = area number
        digits = "".join(c for c in r.script_type if c.isdigit())
        return int(digits) if digits else 0
    return idx - 1                                   # E / B / F (one bit per object)


def allocate(results: list[RowResult], params: dict) -> list[DiagBlock]:
    min_b = int(params.get("diag_bit_min", 0) or 0)
    max_b = int(params.get("diag_bit_max", 62) or 62)
    cap = max_b - min_b + 1

    diag = [r for r in results if r.type_def and r.type_def.in_diag and not r.skipped]
    project_fu = _common_fu(diag)

    node_based = [r for r in diag if not (r.family and r.family.diag_block)]      # A/W/KQ/PA/PW
    fam_based = [r for r in diag if r.family and r.family.diag_block and str(r.index).strip().isdigit()]

    # --- Field inference: a node that needs exactly one bit AND it's a lone PA/PW -> +FieldIODevices.
    by_fl: dict[str, list[RowResult]] = defaultdict(list)
    for r in node_based:
        by_fl[r.iorow.node_fl].append(r)
    node_fls: list[str] = []        # node_fl in first-appearance (row) order -> Type-1 cabinets
    field_rows: list[RowResult] = []
    seen: set[str] = set()
    for r in node_based:            # row order
        fl = r.iorow.node_fl
        if fl in seen:
            continue
        seen.add(fl)
        rs = by_fl[fl]
        if len(rs) == 1 and rs[0].type_def.is_p_type:
            field_rows.append(rs[0])
        else:
            node_fls.append(fl)

    # --- build the ordered block list + an id map; ID_Local == ID_SWP (kept equal upstream).
    blocks: list[DiagBlock] = []
    node_id: dict[str, int] = {}
    type2_id: dict[tuple[str, int], int] = {}
    idc = 0
    for fl in node_fls:                                # Type-1 node cabinets first
        rep = by_fl[fl][0].iorow
        blocks.append(DiagBlock(idc, rep.functional_unit, rep.location,
                                rep.functional_unit + rep.location, 1, BlockKind.TYPE1_FL))
        node_id[fl] = idc
        idc += 1

    fam_p = {id(r): _family_offset(r) for r in fam_based}
    by_block: dict[str, list[RowResult]] = defaultdict(list)
    for r in fam_based:
        by_block[r.family.diag_block].append(r)

    def _add_type2(stem: str, n_instances: int) -> None:
        nonlocal idc
        for inst in range(1, n_instances + 1):
            loc = f"{stem}_{inst}"
            blocks.append(DiagBlock(idc, project_fu, loc, project_fu + loc, 2,
                                    BlockKind.TYPE2_GENERATED, family=stem, instance=inst))
            type2_id[(stem, inst)] = idc
            idc += 1

    if field_rows:
        _add_type2(_FIELD, (len(field_rows) - 1) // cap + 1)
    for stem in _TYPE2_ORDER:
        if stem == _FIELD or stem not in by_block:
            continue
        _add_type2(stem, max(fam_p[id(r)] for r in by_block[stem]) // cap + 1)
    for stem, rs in by_block.items():                  # any family block not in the canonical order
        if stem not in _TYPE2_ORDER:
            _add_type2(stem, max(fam_p[id(r)] for r in rs) // cap + 1)

    # --- assign AE/AF.
    # node cabinets: non-P from min UP, P from max DOWN, in row order.
    nonp = {fl: min_b for fl in node_fls}
    pdown = {fl: max_b for fl in node_fls}
    for r in sorted(node_based, key=lambda r: (r.iorow.sheet, r.iorow.row)):
        fl = r.iorow.node_fl
        if fl not in node_id:                          # this lone P-type went to +FieldIODevices
            continue
        if r.type_def.is_p_type:
            bit = pdown[fl]; pdown[fl] -= 1
        else:
            bit = nonp[fl]; nonp[fl] += 1
        r.diag_cabinet = f"{node_id[fl]:03d}"
        r.diag_bit = f"{bit:02d}"

    # +FieldIODevices: P-types from the top, with rollover (filling by capacity).
    for i, r in enumerate(field_rows):
        cid = type2_id[(_FIELD, i // cap + 1)]
        r.diag_cabinet = f"{cid:03d}"
        r.diag_bit = f"{max_b - (i % cap):02d}"

    # Type-2 family blocks: per-family offset -> instance + bit (from min up), with rollover.
    for r in fam_based:
        p = fam_p[id(r)]
        cid = type2_id[(r.family.diag_block, p // cap + 1)]
        r.diag_cabinet = f"{cid:03d}"
        r.diag_bit = f"{min_b + (p % cap):02d}"

    return blocks
