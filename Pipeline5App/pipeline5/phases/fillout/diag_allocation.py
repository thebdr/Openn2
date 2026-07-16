"""ph200 / 230 + 240 §8 DIAGNOSIS allocation - the diag_cabinet (AE) + diag_bit (AF) columns and the
ordered DiagBlock list. A faithful clean-room port of PL3's `domain/iolist_diag/diag_alloc.py::allocate`
into PL4's SSOT model (a STAGED signals dict per row, mirroring `index_assign.py`).

Only in_diag rows get a cabinet/bit. Rows split into node-based (no family / a family with no Type-2
diag_block: A/W/KQ/PA/PW) -> physical node cabinets (Type-1), and family-based (a family with a diag_block
set: doors/encoders/breakers/fire/emergency PB/areas) -> generated Type-2 blocks. A lone PA/PW on a node is
inferred into the shared +FieldIODevices block. Node cabinets: non-P bits grow UP from diag_bit_min, P bits
grow DOWN from diag_bit_max. Type-2 family blocks grow UP; +FieldIODevices DOWN. Idempotent: a cabinet's id
is STABLE (reused by full_name via `existing`), bits CONTINUE PAST those already used in a cabinet (seeded
from each row's ex_diag_bit/ex_diag_cabinet), Type-2 family bits are a deterministic function of the signal.

PL4 ADAPTER (a STAGED signals dict `r` -> the PL3 row concepts), all on the `_Res` accumulator:
- in_diag:     (r["type"] or {}).get("in_diag")          [PL4 key is "in_diag", NOT PL3's "in_diagnosis"]
- is_p:        (r["type"] or {}).get("type_id","").upper() in {"PA","PW"}
- channel:     (r["type"] or {}).get("channel","")
- family:      family_for(r["script_type"], families)     (its .diag_block / .key drive node-vs-Type-2 + offset)
- index:       r.get("index","")                          (fam_based requires str(index).isdigit())
- node_fl:     r["functional_unit"] + r["location"]
- script_type: r["script_type"]
- ex_diag_bit / ex_diag_cabinet: r.get("diag_bit","") / r.get("diag_cabinet","")   (idempotency seeds)
- sheet/row:   (r.get("source_sheet",""), int(r.get("source_row") or 0))            (node-row sort)
- skipped:     False  (staging already drops skip rows)

`allocate(rows, families, params, existing=None) -> (blocks, placements)`: `blocks` is the ordered list of
DiagBlock records (id_local/fu/location/full_name/template_type/family/instance); `placements` maps each
in_diag row's uid -> (diag_cabinet, diag_bit) as 3-digit / 2-digit strings.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

from pipeline5 import config
from pipeline5.phases.fillout.type_families import family_for


def diag_bit_range(params) -> tuple:
    """The (min, max) diagnosis bit range from `iolist_params.diag_bits_range` ([min, max], inclusive;
    default (0, 62)). The single source - node non-P bits grow UP from min, P bits DOWN from max."""
    rng = config.get_param(params, "iolist_params.diag_bits_range", None)
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        return int(rng[0]), int(rng[1])
    return 0, 62

_FIELD = "+FieldIODevices"
_TYPE2_ORDER = [
    _FIELD, "+SafetyDoors", "+SafetyEncoders", "+SafetyBreakers",
    "+FireAlarm", "+EmergencyPushButtons", "+EmergencyAreas",
]
_P_TYPES = {"PA", "PW"}


@dataclass(frozen=True)
class DiagBlock:
    """A diagnosis cabinet (Type-1 = a physical node FL; Type-2 = a generated family block)."""
    id_local: int
    fu: str
    location: str
    full_name: str
    template_type: int                   # 1 = node FL; 2 = generated
    family: str = ""
    instance: int = 0


# --- a mutable per-row accumulator (the PL3 RowResult analog, like index_assign._Res) ---------- #
class _Res:
    __slots__ = ("r", "uid", "script_type", "type_def", "family", "index", "node_fl",
                 "sheet", "row", "ex_diag_bit", "ex_diag_cabinet", "skipped",
                 "diag_cabinet", "diag_bit")

    def __init__(self, r, families):
        self.r = r
        self.uid = r["uid"]
        self.script_type = r.get("script_type") or ""
        self.type_def = r.get("type") or {}
        self.family = family_for(self.script_type, families)
        self.index = r.get("index", "")
        self.node_fl = f"{r.get('functional_unit', '')}{r.get('location', '')}"
        self.sheet = r.get("source_sheet", "")
        try:
            self.row = int(r.get("source_row") or 0)
        except (TypeError, ValueError):
            self.row = 0
        self.ex_diag_bit = r.get("diag_bit", "")
        self.ex_diag_cabinet = r.get("diag_cabinet", "")
        self.skipped = False
        self.diag_cabinet = ""
        self.diag_bit = ""

    @property
    def in_diag(self) -> bool:
        return bool(self.type_def.get("in_diag"))

    @property
    def is_p(self) -> bool:
        return (self.type_def.get("type_id", "") or "").upper() in _P_TYPES

    @property
    def channel(self) -> str:
        return self.type_def.get("channel", "") or ""


def _family_offset(r: _Res) -> int:
    """0-based bit offset within a Type-2 family block (PL3 `_family_offset`, verbatim)."""
    idx = int(r.index)
    key = r.family.key.upper()
    if key == "N":                               # encoder: two channels per index
        return (idx - 1) * 2 + (0 if r.channel == "1" else 1)
    if key == "D":                               # door: DI at base+1, DD at base+2 (bit 0 reserved per pair)
        base = (idx - 1) * 2
        return base + 1 if (r.script_type or "").upper().startswith("DI") else base + 2
    if key == "Z":                               # emergency area: bit = the area number
        digits = "".join(c for c in (r.script_type or "") if c.isdigit())
        return int(digits) if digits else 0
    return idx - 1                               # E / B / F: one bit per object


def allocate(rows: list, families: list, params: dict, existing: dict | None = None) -> tuple:
    """Compute (blocks, placements) for the staged signal rows. `existing` maps an existing cabinet's
    full_name -> int(cabinet_id) (stable-id idempotency); each row's ex_diag_* seed the bit allocation."""
    min_b, max_b = diag_bit_range(params)
    cap = max_b - min_b + 1

    results = [_Res(r, families) for r in rows]

    diag = [r for r in results if r.type_def and r.in_diag and not r.skipped]
    node_based = [r for r in diag if not (r.family and r.family.diag_block)]
    fam_based = [r for r in diag if r.family and r.family.diag_block and str(r.index).isdigit()]
    project_fu = next((r.r.get("functional_unit", "") for r in diag if r.r.get("functional_unit")), "")

    # --- field inference: a lone PA/PW on a node -> +FieldIODevices instead of a dedicated cabinet --- #
    by_fl = defaultdict(list)
    for r in node_based:
        by_fl[r.node_fl].append(r)
    node_fls, field_rows, seen = [], [], set()
    for r in node_based:
        fl = r.node_fl
        if fl in seen:
            continue
        seen.add(fl)
        rs = by_fl[fl]
        if len(rs) == 1 and rs[0].is_p:
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
        rep = by_fl[fl][0].r
        fu = rep.get("functional_unit", "")
        loc = rep.get("location", "")
        fn = fu + loc
        cid = _id_for(fn)
        blocks.append(DiagBlock(id_local=cid, fu=fu, location=loc, full_name=fn, template_type=1))
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
    node_rows = [r for r in sorted(node_based, key=lambda r: (r.sheet, r.row))
                 if r.node_fl in node_id]
    for r in node_rows:                          # seed each cabinet's used bits from already-filled rows
        b = _bit_int(r.ex_diag_bit)
        if b is not None:
            used_bits[node_id[r.node_fl]].add(b)
    nonp = {fl: min_b for fl in node_fls}
    pdown = {fl: max_b for fl in node_fls}
    for r in node_rows:
        fl = r.node_fl
        cab = node_id[fl]
        r.diag_cabinet = f"{cab:03d}"
        ex = _bit_int(r.ex_diag_bit)
        if ex is not None:                       # keep an already-assigned bit
            r.diag_bit = f"{ex:02d}"
            continue
        if r.is_p:
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
        b, c = _bit_int(r.ex_diag_bit), _bit_int(r.ex_diag_cabinet)
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
        ex_b, ex_c = _bit_int(r.ex_diag_bit), _bit_int(r.ex_diag_cabinet)
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

    placements = {r.uid: (r.diag_cabinet, r.diag_bit) for r in diag
                  if r.diag_cabinet or r.diag_bit}
    return blocks, placements
