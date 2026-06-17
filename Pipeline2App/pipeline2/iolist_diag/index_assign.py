"""Task B - index (AD): per-family contiguous progressive with object grouping (spec §7).

The index is a zero-padded 4-digit progressive assigned per script_type family, in I/O-list row
order, over the non-skipped typed rows. Multi-signal objects share one index: an *anchor* row
consumes the family counter and its siblings inherit it.

Grouping is registry-driven (object_families.csv):
  - channel (E/B/N/F): anchor = channel "1"; the "2" channel inherits by EXACT FLD (mismatch /
    orphan = data-entry defect -> error, never guessed - §7.2);
  - series   (K): KQ consumes the counter; a KI inherits the KQ that shares its FLD (the primary
    KI / KI1/n), and KI2/n..KIn/n inherit that group's index (FLDs may legitimately differ);
  - fld      (door): anchor = DI1/2; DD and DI2/2 inherit by the door-sensor FLD; DR/DL/DQ sit on
    a relay/PLC input and can't be auto-linked -> <input required> (§7.3);
  - pattern  (Z): the whole family is one object sharing a single index (bit = area number);
  - none     (R) and the non-family diag types (A/W/PA/PW): every row consumes its own counter.

A row that can't be auto-resolved gets the `<input required>` marker (unless a human already
filled its index, which is preserved) and is reported (§10). Counters seed from existing numeric
indices so a re-run is idempotent and a fresh list numbers 0001, 0002, ... with no gaps.
"""
from __future__ import annotations
from enum import Enum, auto

from pipeline2.iolist_diag.models import Category, INPUT_REQUIRED, LinkKind, RowResult

_DOOR_MANUAL = {"DR", "DL", "DQ"}


class Role(Enum):
    STANDALONE = auto()      # A/W/PA/PW: own counter keyed by script_type
    ANCHOR = auto()          # consumes the family counter (channel-1, KQ, DI1/2)
    CHANNEL_2 = auto()       # E/B/N/F channel 2: inherit the anchor by FLD (strict)
    SERIES_PRIMARY = auto()  # KI bare / KI1/n: inherit the KQ that shares its FLD
    SERIES_SIBLING = auto()  # KIx/n (x>=2): inherit the current series group's index
    FLD_INHERIT = auto()     # door DD / DI2/2: inherit DI1/2 by FLD
    MANUAL = auto()          # door DR/DL/DQ: <input required>
    PATTERN = auto()         # Z: one shared index for the family
    RESET = auto()           # R: each row consumes the counter (no grouping)


def is_indexable(r: RowResult) -> bool:
    """A row that should receive an index: not skipped, a real script_type (an unmatched
    `<input required>` type is handled upstream as unresolved-type), and not an Interface coupler.
    A catalogue type is indexed; a family-mapped type that the catalogue doesn't list verbatim
    (e.g. a per-area reset `R2` when only the `R*` pattern exists) is still indexed via its family."""
    if r.skipped or r.script_type in ("", INPUT_REQUIRED):
        return False
    if r.type_def is not None:
        return r.type_def.category != Category.INTERFACE
    return r.family is not None


def role_of(r: RowResult) -> Role:
    fam = r.family
    if fam is None:
        return Role.STANDALONE
    st = r.script_type.upper()
    ch = r.type_def.channel if r.type_def else ""
    match fam.link:
        case LinkKind.NONE:
            return Role.RESET
        case LinkKind.PATTERN:
            return Role.PATTERN
        case LinkKind.CHANNEL:
            return Role.ANCHOR if ch == "1" else Role.CHANNEL_2
        case LinkKind.SERIES:
            if st.startswith("KQ"):
                return Role.ANCHOR
            return Role.SERIES_PRIMARY if ch in ("", "1") else Role.SERIES_SIBLING
        case LinkKind.FLD:
            if st in _DOOR_MANUAL:
                return Role.MANUAL
            if st.startswith("DI") and ch == "1":
                return Role.ANCHOR
            return Role.FLD_INHERIT       # DD, DI2/2
    return Role.STANDALONE


def _counter_key(r: RowResult) -> str:
    return r.script_type.upper() if r.family is None else r.family.key.upper()


def _take(counters: dict, key: str, ex_index: str) -> str:
    """Next index for `key`: preserve an existing numeric index (and advance the counter past it)
    so re-runs are idempotent; otherwise the next contiguous 0001/0002/... value."""
    n = counters.get(key, 0)
    ex = (ex_index or "").strip()
    if ex.isdigit():
        counters[key] = max(n, int(ex))
        return ex
    counters[key] = n + 1
    return f"{n + 1:04d}"


def _unresolved(r: RowResult, reason: str, error: bool = False) -> None:
    """Mark an index that can't be auto-resolved. A *real* human-filled index is preserved (then it is
    NOT unresolved); an empty cell OR a leftover `<input required>` marker from a prior run stays
    unresolved (so a re-run still flags it and the §11 halt still fires)."""
    ex = r.iorow.ex_index.strip()
    if ex and ex != INPUT_REQUIRED:
        r.index = ex
        return
    r.unresolved = True
    r.unresolved_reason = reason
    r.index = INPUT_REQUIRED
    if error:
        r.error = reason


def assign_indices(results: list[RowResult], families) -> list[RowResult]:
    """Assign `index` on every indexable row in `results` (mutates them). `families` is unused
    directly (each row already carries its `family`) but kept for symmetry / future rules."""
    rows = [r for r in results if is_indexable(r)]
    counters: dict[str, int] = {}
    fld_anchor: dict[str, dict[str, str]] = {}   # family.key -> {fld: index}
    pattern_idx: dict[str, str] = {}             # family.key -> shared index

    # Pass 1 - anchors / standalone / reset / pattern, in row order (consume the counters).
    for r in rows:
        role = role_of(r)
        if role in (Role.STANDALONE, Role.ANCHOR, Role.RESET):
            r.index = _take(counters, _counter_key(r), r.iorow.ex_index)
            if role == Role.ANCHOR:
                fld_anchor.setdefault(r.family.key, {})[r.iorow.fld] = r.index
        elif role == Role.PATTERN:
            key = r.family.key
            if key not in pattern_idx:
                pattern_idx[key] = _take(counters, key, r.iorow.ex_index)
            r.index = pattern_idx[key]

    # Pass 2 - channel-2 + door inherit by FLD (anchors of every family are now registered).
    for r in rows:
        role = role_of(r)
        if role == Role.CHANNEL_2:
            idx = fld_anchor.get(r.family.key, {}).get(r.iorow.fld)
            if idx:
                r.index = idx
            else:
                _unresolved(r, "channel_fld_mismatch", error=True)   # §7.2 data-entry defect
        elif role == Role.FLD_INHERIT:
            idx = fld_anchor.get("D", {}).get(r.iorow.fld)
            if idx:
                r.index = idx
            else:
                _unresolved(r, "door_member_unlinked")
        elif role == Role.MANUAL:
            _unresolved(r, "manual_member")                          # §7.3 DR/DL/DQ

    # §7.2 orphan check - a channel-1 anchor with no channel-2 partner sharing its device (FLD) is a
    # data-entry defect (symmetric to the channel-2 orphan handled above), so flag it as an error too.
    ch2_flds: dict[str, set] = {}
    for r in rows:
        if r.family and r.family.link == LinkKind.CHANNEL and role_of(r) == Role.CHANNEL_2:
            ch2_flds.setdefault(r.family.key, set()).add(r.iorow.fld)
    for r in rows:
        if r.family and r.family.link == LinkKind.CHANNEL and role_of(r) == Role.ANCHOR:
            if r.iorow.fld not in ch2_flds.get(r.family.key, set()):
                _unresolved(r, "channel_fld_mismatch", error=True)

    # Pass 3 - series (K) in row order: a primary KI inherits its KQ (by FLD); a KIx/n sibling inherits
    # the group ONLY while it continues the same contiguous KI1/n..KIn/n run (same /n total + next row).
    # A stray sibling (missing primary, or after a different group) must NOT borrow the leftover index
    # (§7.2/§7.3 - "do not invent an index for these") - it goes to the report instead.
    current: str | None = None
    current_total = ""
    prev_row = -1
    for r in rows:
        if not (r.family and r.family.link == LinkKind.SERIES):
            continue
        role = role_of(r)
        if role == Role.ANCHOR:                  # KQ: already assigned in pass 1
            continue
        st = r.script_type.upper()
        total = st.split("/")[-1] if "/" in st else ""
        if role == Role.SERIES_PRIMARY:
            current = fld_anchor.get("K", {}).get(r.iorow.fld)
            current_total, prev_row = total, r.iorow.row
            if current:
                r.index = current
            else:
                _unresolved(r, "ki_without_kq")
        elif role == Role.SERIES_SIBLING:
            if current and total == current_total and r.iorow.row == prev_row + 1:
                r.index = current
                prev_row = r.iorow.row
            else:
                _unresolved(r, "ki_without_kq")
                current = None                   # the run is broken; don't leak it to later siblings
    return results
