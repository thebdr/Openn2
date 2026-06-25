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


def allocate(results: list, params: dict, existing: dict | None = None) -> list:
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

    # IDs are STABLE per cabinet: reuse an existing block's id (keyed by full_name) so a re-run never
    # renumbers; a brand-new cabinet gets the next free id above every existing one (orphans stay reserved).
    existing = existing or {}
    used_ids = set(existing.values())
    next_id = max(existing.values(), default=-1) + 1

    def _id_for(full_name: str) -> int:
        nonlocal next_id
        if full_name in existing:
            return existing[full_name]
        while next_id in used_ids:
            next_id += 1
        nid = next_id
        used_ids.add(nid)
        next_id += 1
        return nid

    blocks, node_id, type2_id = [], {}, {}

    # Type-1 node cabinets first (node_fl row order)
    for fl in node_fls:
        rep = by_fl[fl][0].iorow
        fn = rep.functional_unit + rep.location
        cid = _id_for(fn)
        blocks.append(DiagBlock(id_local=cid, fu=rep.functional_unit, location=rep.location,
                                full_name=fn, template_type=1))
        node_id[fl] = cid

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
            fn = project_fu + loc
            cid = _id_for(fn)
            blocks.append(DiagBlock(id_local=cid, fu=project_fu, location=loc,
                                    full_name=fn, template_type=2, family=stem, instance=inst))
            type2_id[(stem, inst)] = cid

    # --- bit allocation (idempotent) --- #
    # A blank row's bit CONTINUES PAST the bits already used in its cabinet (seeded from rows that already
    # carry a diag_bit), so a re-run never assigns a colliding (cabinet, bit); a row that already has a bit
    # keeps it. Node cabinets + +FieldIODevices are SEQUENTIAL (seeded next-free); Type-2 family bits are a
    # deterministic function of the signal (already collision-free). A fresh fill == the previous behaviour.
    def _bit_int(v):
        s = str(v).strip() if v is not None else ""
        return int(s) if s.lstrip("-").isdigit() else None

    # node cabinets: non-P grow UP from diag_bit_min, P grow DOWN from diag_bit_max, skipping used bits
    used_bits = defaultdict(set)
    node_rows = [r for r in sorted(node_based, key=lambda r: (r.iorow.sheet, r.iorow.row))
                 if r.iorow.node_fl in node_id]
    for r in node_rows:                          # seed each cabinet's used bits from already-filled rows
        b = _bit_int(r.iorow.ex_diag_bit)
        if b is not None:
            used_bits[node_id[r.iorow.node_fl]].add(b)
    nonp = {fl: min_b for fl in node_fls}
    pdown = {fl: max_b for fl in node_fls}
    for r in node_rows:
        fl = r.iorow.node_fl
        cab = node_id[fl]
        r.diag_cabinet = f"{cab:03d}"
        ex = _bit_int(r.iorow.ex_diag_bit)
        if ex is not None:                       # keep an already-assigned bit
            r.diag_bit = f"{ex:02d}"
            continue
        if td_is_p(r.type_def):
            b = pdown[fl]
            while b in used_bits[cab]:
                b -= 1
            pdown[fl] = b - 1
        else:
            b = nonp[fl]
            while b in used_bits[cab]:
                b += 1
            nonp[fl] = b + 1
        used_bits[cab].add(b)
        r.diag_bit = f"{b:02d}"

    # +FieldIODevices: cap-wide instances filled DOWNWARD from diag_bit_max; keep an existing row's
    # (cabinet, bit), pour each new row into the first free (instance, bit) slot.
    field_insts = sorted(inst for (stem, inst) in type2_id if stem == _FIELD)
    cid_of_inst = {inst: type2_id[(_FIELD, inst)] for inst in field_insts}
    inst_of_cid = {cid: inst for inst, cid in cid_of_inst.items()}
    field_used = {inst: set() for inst in field_insts}
    for r in field_rows:
        b, c = _bit_int(r.iorow.ex_diag_bit), _bit_int(r.iorow.ex_diag_cabinet)
        if b is not None and c in inst_of_cid:
            field_used[inst_of_cid[c]].add(b)

    def _next_field_slot():
        for inst in field_insts:
            for bit in range(max_b, min_b - 1, -1):
                if bit not in field_used[inst]:
                    field_used[inst].add(bit)
                    return inst, bit
        return None, None

    for r in field_rows:
        ex_b, ex_c = _bit_int(r.iorow.ex_diag_bit), _bit_int(r.iorow.ex_diag_cabinet)
        if ex_b is not None and ex_c is not None:
            r.diag_cabinet = f"{ex_c:03d}"
            r.diag_bit = f"{ex_b:02d}"
            continue
        inst, bit = _next_field_slot()
        if inst is None:
            continue
        r.diag_cabinet = f"{cid_of_inst[inst]:03d}"
        r.diag_bit = f"{bit:02d}"

    # Type-2 family blocks: the bit is a deterministic function of the signal's index/channel
    for r in fam_based:
        p = _family_offset(r)
        cid = type2_id[(r.family.diag_block, p // cap + 1)]
        r.diag_cabinet = f"{cid:03d}"
        r.diag_bit = f"{min_b + (p % cap):02d}"

    return blocks
