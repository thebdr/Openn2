"""Render value-objects for the rich validation report (phase 100) - the optional payload a `Finding`
carries so `io/render.py` can reproduce PL3's aligned report line. Clean-room port of the `InfoBlock` +
`Cmp` from PL3's `core/model.py` (PL4 replaced PL3's `LogEntry` with `core.finding.Finding`; these two
value objects are the part of the old model the rich validation reporting still needs).

Non-validation phases never populate these (their findings leave `info`/`cmp` as None), so the universal
Finding stays lean; only the 110-150 validators fill them. Both are hashable (frozen / namedtuple) so a
`Finding` carrying one stays hashable.
"""
from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass

# A cross-check comparison (130/140): the caller-side vs the other-workbook value, for the IO ADDRESS and
# the FLD, each with its equality flag. The renderer aligns the four fields per-phase and prints
# `<addr> op <addr> | <fld> op <fld>` with op = `===` (equal) / `=/=` (differ).
Cmp = namedtuple("Cmp", "caller_addr other_addr addr_eq caller_fld other_fld fld_eq")


@dataclass(frozen=True)
class InfoBlock:
    """The fixed middle of a rendered validation line; blank fields render empty."""
    bit: str = ""
    fld: str = ""
    desc_l1: str = ""
    desc_l1b: str = ""
    drawing: str = ""
    type_index: str = ""

    def cells(self) -> list:
        return [self.bit, self.fld, self.desc_l1, self.desc_l1b, self.drawing, self.type_index]
