"""ph200 / 220 INDEX assignment (the §7 per-family contiguous progressive index, in I/O-list row
order, with object grouping: channel pairs by FLD, KQ<->KI series, door FLD, Z pattern, standalone).
Unresolvable members get the `<input required>` sentinel (and a reason). A faithful clean-room port
of PL3's `domain/iolist_diag/index_assign.py` into PL4's SSOT model.

PL4 ADAPTER (a STAGED signals dict `r` -> the PL3 row concepts):
- skipped:     False always (staging already drops skip-reason/struck rows).
- script_type: r["script_type"]
- type_def:    r["type"] (a dict or None); td_is_interface = category=='interface'; td_channel = channel.
- family:      family_for(r["script_type"], families)  (longest-prefix).
- fld:         r["functional_unit"] + r["location"] + r["device"]   (== PL3 iorow.fld).
- row (order): int(r.get("source_row") or 0)                        (== PL3 iorow.row, contiguity).
- ex_index:    "" when from_scratch else r.get("index","")          (== PL3 iorow.ex_index, idempotency).
- uid:         r["uid"]  (the result-map key).

`assign_indices(rows, families, *, from_scratch=False) -> dict{uid: index}` returns an entry for EVERY
is_indexable row (the others get none).
"""
from __future__ import annotations
from collections import defaultdict

from pipeline4.domain.fillout.families import (
    family_for, LINK_CHANNEL, LINK_SERIES, LINK_FLD, LINK_PATTERN, LINK_NONE,
)
from pipeline4.domain.fillout.ranges import expand_range_fld

INPUT_REQUIRED = "<input required>"


def _register_anchor(anchor_map: dict, fld: str, index: str) -> None:
    """Register an anchor's index under its FLD AND each range-expanded component FLD, so a member authored
    as the range OR as an independent component matches it (the exact FLD wins; expansion fills the rest)."""
    for f in expand_range_fld(fld):
        anchor_map.setdefault(f, index)
    anchor_map[fld] = index


def _anchor_lookup(anchor_map: dict, fld: str):
    """An anchor index for `fld`: the exact FLD first, then (bidirectional) any range-expanded component of
    `fld` - so an independent member finds a range anchor AND a range member finds an independent anchor."""
    if fld in anchor_map:
        return anchor_map[fld]
    for comp in expand_range_fld(fld):
        if comp in anchor_map:
            return anchor_map[comp]
    return None

# roles
STANDALONE, ANCHOR, CHANNEL_2, RESET, PATTERN = "standalone", "anchor", "channel_2", "reset", "pattern"
SERIES_PRIMARY, SERIES_SIBLING, FLD_INHERIT, MANUAL = "series_primary", "series_sibling", "fld_inherit", "manual"


# --- the PL4 adapter helpers over a staged signals dict ---------------------------------------- #
def _td_is_interface(type_def) -> bool:
    return (type_def or {}).get("category", "").lower() == "interface"


def _td_channel(type_def) -> str:
    return (type_def or {}).get("channel", "")


def _fld(r) -> str:
    return f"{r.get('functional_unit', '')}{r.get('location', '')}{r.get('device', '')}"


def _row_order(r) -> int:
    try:
        return int(r.get("source_row") or 0)
    except (TypeError, ValueError):
        return 0


# --- a mutable per-row accumulator (the PL3 RowResult analog) ----------------------------------- #
class _Res:
    __slots__ = ("r", "uid", "script_type", "type_def", "family", "ex_index",
                 "fld", "row", "index", "unresolved", "unresolved_reason", "error")

    def __init__(self, r, families, ex_index):
        self.r = r
        self.uid = r["uid"]
        self.script_type = r.get("script_type") or ""
        self.type_def = r.get("type") or None
        self.family = family_for(self.script_type, families)
        self.ex_index = ex_index
        self.fld = _fld(r)
        self.row = _row_order(r)
        self.index = ""
        self.unresolved = False
        self.unresolved_reason = ""
        self.error = ""


def is_indexable(res) -> bool:
    # PL4: every staged signal is non-skipped.
    st = (res.script_type or "").strip()
    if not st or st == INPUT_REQUIRED:
        return False
    return (res.type_def is not None and not _td_is_interface(res.type_def)) or (res.family is not None)


def role_of(res) -> str:
    fam = res.family
    if fam is None:
        return STANDALONE
    st = (res.script_type or "").upper()
    ch = _td_channel(res.type_def)
    if fam.link == LINK_NONE:
        return RESET
    if fam.link == LINK_PATTERN:
        return PATTERN
    if fam.link == LINK_CHANNEL:
        return ANCHOR if ch == "1" else CHANNEL_2
    if fam.link == LINK_SERIES:
        if st.startswith("KQ"):
            return ANCHOR
        return SERIES_PRIMARY if ch in ("", "1") else SERIES_SIBLING
    if fam.link == LINK_FLD:
        if st.startswith("DI") and ch == "1":
            return ANCHOR
        if st.startswith("DD") or (st.startswith("DI") and ch == "2"):
            return FLD_INHERIT
        return MANUAL
    return STANDALONE


def _counter_key(res) -> str:
    return res.family.key.upper() if res.family is not None else (res.script_type or "").upper()


def _take(counters: dict, key: str, ex_index: str) -> str:
    n = counters.get(key, 0)
    ex = (ex_index or "").strip()
    if ex.isdigit():
        counters[key] = max(n, int(ex))
        return ex
    counters[key] = n + 1
    return f"{n + 1:04d}"


def _unresolved(res, reason: str, error: bool = False) -> None:
    ex = (res.ex_index or "").strip()
    if ex and ex != INPUT_REQUIRED:
        res.index = ex                    # a genuine human entry -> preserve, not unresolved
        return
    res.unresolved = True
    res.unresolved_reason = reason
    res.index = INPUT_REQUIRED
    if error:
        res.error = reason


def assign_indices(rows: list, families: list, *, from_scratch: bool = False) -> dict:
    """Compute the INDEX per is_indexable staged signal row -> {uid: index}. `from_scratch` blanks the
    pre-filled index (a fresh compute); otherwise a digit ex_index seeds/preserves the counter."""
    results = [_Res(r, families, "" if from_scratch else (r.get("index") or "")) for r in rows]

    counters: dict = {}
    fld_anchor: dict = defaultdict(dict)     # family.key -> {fld -> index}
    pattern_idx: dict = {}                    # family.key -> shared index
    indexable = [res for res in results if is_indexable(res)]

    # Pass 1: anchors / standalone / reset / pattern consume their counters in row order
    for res in indexable:
        role = role_of(res)
        if role in (ANCHOR, STANDALONE, RESET):
            res.index = _take(counters, _counter_key(res), res.ex_index)
            if role == ANCHOR:
                _register_anchor(fld_anchor[res.family.key], res.fld, res.index)
        elif role == PATTERN:
            key = res.family.key
            if key not in pattern_idx:
                pattern_idx[key] = _take(counters, key, res.ex_index)
            res.index = pattern_idx[key]

    # Pass 2: channel-2 inherit by FLD; door members; manual; symmetric orphan check
    ch2_flds: dict = defaultdict(set)
    for res in indexable:
        if role_of(res) == CHANNEL_2:
            ch2_flds[res.family.key].add(res.fld)
    for res in indexable:
        role = role_of(res)
        if role == CHANNEL_2:
            got = _anchor_lookup(fld_anchor.get(res.family.key, {}), res.fld)
            if got:
                res.index = got
            else:
                _unresolved(res, "channel_fld_mismatch", error=True)
        elif role == FLD_INHERIT:
            got = _anchor_lookup(fld_anchor.get("D", {}), res.fld)
            if got:
                res.index = got
            else:
                _unresolved(res, "door_member_unlinked")
        elif role == MANUAL:
            _unresolved(res, "manual_member")
        elif role == ANCHOR and res.family.link == LINK_CHANNEL:
            if res.fld not in ch2_flds.get(res.family.key, set()):
                _unresolved(res, "channel_fld_mismatch", error=True)

    # Pass 3: K series (KQ anchor already done) - KI primary inherits KQ by FLD; siblings need contiguity
    current = None
    current_total = ""
    prev_row = -10
    for res in indexable:
        if not (res.family is not None and res.family.link == LINK_SERIES):
            continue
        role = role_of(res)
        if role == ANCHOR:
            continue
        st = (res.script_type or "").upper()
        total = st.split("/")[-1] if "/" in st else ""
        if role == SERIES_PRIMARY:
            current = _anchor_lookup(fld_anchor.get("K", {}), res.fld)
            current_total = total
            prev_row = res.row
            if current:
                res.index = current
            else:
                _unresolved(res, "ki_without_kq")
        elif role == SERIES_SIBLING:
            if current and total == current_total and res.row == prev_row + 1:
                res.index = current
                prev_row = res.row
            else:
                _unresolved(res, "ki_without_kq")
                current = None

    return {res.uid: res.index for res in indexable}
