"""ph200 device-tag RANGE notation (`-K66701..2`) - the trailing-digit range and its components.

A device (and therefore the FLD that ends in it) can carry a range in its trailing digit: `-K66701..2`
expands to the components `-K66701`, `-K66702` (the last digit runs from the base value to N, left->right).
The same multi-channel family can be authored EITHER as the range form OR as the independent component rows;
the fill expands every range FLD into its components so the two forms match, and derives each component's
channel position `n` of `N` (the `<n>/<N>` script_type suffix). Used by `classify` (the suffix) +
`index_assign` (range-aware FLD grouping).
"""
from __future__ import annotations

import re

# a trailing-digit range at the END of an FLD/device: <base><start>..<end> (single trailing digit each side).
_RANGE_RE = re.compile(r"^(.*?)(\d)\.\.(\d)$")


def range_parts(fld):
    """`(base, start, end)` when `fld` ends in a trailing-digit range (`...<base><start>..<end>`), else None.
    The components are `base + k` for k in `start..end`; e.g. `=S1+DL1.CC1-K66701..2` -> (`=S1+DL1.CC1-K6670`,
    1, 2)."""
    m = _RANGE_RE.match(str(fld or ""))
    if not m:
        return None
    base, start, end = m.group(1), int(m.group(2)), int(m.group(3))
    return (base, start, end) if end >= start else None


def is_range(value) -> bool:
    """True when the string carries a trailing-digit range (the device/FLD form `...N..M`)."""
    return range_parts(value) is not None


def expand_range_fld(fld) -> list:
    """The component FLDs of a range FLD, left->right; a non-range FLD -> `[fld]` unchanged. Idempotent over a
    plain FLD, so callers can expand unconditionally."""
    p = range_parts(fld)
    if not p:
        return [str(fld or "")]
    base, start, end = p
    return [f"{base}{k}" for k in range(start, end + 1)]


def build_channel_map(flds) -> dict:
    """`{component_FLD -> (n, N)}` over the RANGE flds in `flds`: `n` = the component's 1-based position
    left->right, `N` = the number of components. A non-range fld contributes nothing; a component claimed by
    more than one range keeps the FIRST (insertion order)."""
    out: dict = {}
    for fld in flds:
        comps = expand_range_fld(fld)
        if len(comps) <= 1:                      # not a range
            continue
        total = len(comps)
        for i, comp in enumerate(comps, start=1):
            out.setdefault(comp, (i, total))
    return out
