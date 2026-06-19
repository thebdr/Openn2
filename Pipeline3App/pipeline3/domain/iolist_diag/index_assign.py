"""§7 INDEX assignment (column AD): per-family contiguous progressive index, in I/O-list row order,
with object grouping (channel pairs, KQ<->KI series, door FLD, Z pattern, standalone). Unresolvable
members get the <input required> sentinel (and a reason for the report). Clean-room port of Pipeline2.
"""
from __future__ import annotations
from collections import defaultdict

from pipeline3.domain.iolist_diag.models import (
    INPUT_REQUIRED, LINK_CHANNEL, LINK_SERIES, LINK_FLD, LINK_PATTERN, LINK_NONE,
    td_is_interface, td_channel,
)

# roles
STANDALONE, ANCHOR, CHANNEL_2, RESET, PATTERN = "standalone", "anchor", "channel_2", "reset", "pattern"
SERIES_PRIMARY, SERIES_SIBLING, FLD_INHERIT, MANUAL = "series_primary", "series_sibling", "fld_inherit", "manual"


def is_indexable(r) -> bool:
    if r.skipped:
        return False
    st = (r.script_type or "").strip()
    if not st or st == INPUT_REQUIRED:
        return False
    return (r.type_def is not None and not td_is_interface(r.type_def)) or (r.family is not None)


def role_of(r) -> str:
    fam = r.family
    if fam is None:
        return STANDALONE
    st = (r.script_type or "").upper()
    ch = td_channel(r.type_def)
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


def _counter_key(r) -> str:
    return r.family.key.upper() if r.family is not None else (r.script_type or "").upper()


def _take(counters: dict, key: str, ex_index: str) -> str:
    n = counters.get(key, 0)
    ex = (ex_index or "").strip()
    if ex.isdigit():
        counters[key] = max(n, int(ex))
        return ex
    counters[key] = n + 1
    return f"{n + 1:04d}"


def _unresolved(r, reason: str, error: bool = False) -> None:
    ex = (r.iorow.ex_index or "").strip()
    if ex and ex != INPUT_REQUIRED:
        r.index = ex                      # a genuine human entry -> preserve, not unresolved
        return
    r.unresolved = True
    r.unresolved_reason = reason
    r.index = INPUT_REQUIRED
    if error:
        r.error = reason


def assign_indices(results: list, families: list) -> None:
    counters: dict = {}
    fld_anchor: dict = defaultdict(dict)     # family.key -> {fld -> index}
    pattern_idx: dict = {}                    # family.key -> shared index
    indexable = [r for r in results if is_indexable(r)]

    # Pass 1: anchors / standalone / reset / pattern consume their counters in row order
    for r in indexable:
        role = role_of(r)
        if role in (ANCHOR, STANDALONE, RESET):
            r.index = _take(counters, _counter_key(r), r.iorow.ex_index)
            if role == ANCHOR:
                fld_anchor[r.family.key][r.iorow.fld] = r.index
        elif role == PATTERN:
            key = r.family.key
            if key not in pattern_idx:
                pattern_idx[key] = _take(counters, key, r.iorow.ex_index)
            r.index = pattern_idx[key]

    # Pass 2: channel-2 inherit by FLD; door members; manual; symmetric orphan check
    ch2_flds: dict = defaultdict(set)
    for r in indexable:
        if role_of(r) == CHANNEL_2:
            ch2_flds[r.family.key].add(r.iorow.fld)
    for r in indexable:
        role = role_of(r)
        if role == CHANNEL_2:
            got = fld_anchor.get(r.family.key, {}).get(r.iorow.fld)
            if got:
                r.index = got
            else:
                _unresolved(r, "channel_fld_mismatch", error=True)
        elif role == FLD_INHERIT:
            got = fld_anchor.get("D", {}).get(r.iorow.fld)
            if got:
                r.index = got
            else:
                _unresolved(r, "door_member_unlinked")
        elif role == MANUAL:
            _unresolved(r, "manual_member")
        elif role == ANCHOR and r.family.link == LINK_CHANNEL:
            if r.iorow.fld not in ch2_flds.get(r.family.key, set()):
                _unresolved(r, "channel_fld_mismatch", error=True)

    # Pass 3: K series (KQ anchor already done) - KI primary inherits KQ by FLD; siblings need contiguity
    current = None
    current_total = ""
    prev_row = -10
    for r in indexable:
        if not (r.family is not None and r.family.link == LINK_SERIES):
            continue
        role = role_of(r)
        if role == ANCHOR:
            continue
        st = (r.script_type or "").upper()
        total = st.split("/")[-1] if "/" in st else ""
        if role == SERIES_PRIMARY:
            current = fld_anchor.get("K", {}).get(r.iorow.fld)
            current_total = total
            prev_row = r.iorow.row
            if current:
                r.index = current
            else:
                _unresolved(r, "ki_without_kq")
        elif role == SERIES_SIBLING:
            if current and total == current_total and r.iorow.row == prev_row + 1:
                r.index = current
                prev_row = r.iorow.row
            else:
                _unresolved(r, "ki_without_kq")
                current = None
