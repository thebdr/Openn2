"""Task D - (re)generate the DiagnosisBlocks sheet (spec §9).

Header (8 cols, as the golden): ID_Local | ID_SWP | Functional Unit | Location | FullName |
TemplateType | Notes | Count. Rows are emitted Type-1 (FL nodes) first, then Type-2 (generated),
each by ID_Local (the order `diag_alloc.allocate` returns them). `ID_Local == ID_SWP` so both the
spec's join (diag_cabinet -> ID_Local) and staging.load_diagnostic_blocks (keyed by ID_SWP) agree.

NOTE on the columns staging reads (ID_SWP, FullName, TemplateType): they are written as
materialized VALUES, not as the golden's `_TRO_TRAILING`/`VSTACK` spill formulas. staging reads the
sheet with data_only=True and openpyxl can't cache a formula's result, so a formula would read back
as None and break the diag join; the populator regenerates the whole sheet each run, so the dynamic
spill isn't needed. FullName / Functional Unit start with '=' (e.g. "=S1+MC1.CC1"), so they are
forced to text (data_type 's') - otherwise openpyxl would store them as formulas.
"""
from __future__ import annotations
from collections import Counter

from pipeline2.iolist_diag.models import DIAGBLOCKS_SHEET, DiagBlock, RowResult

_HEADERS = ["ID_Local", "ID_SWP", "Functional Unit", "Location",
            "FullName", "TemplateType", "Notes", "Count"]


def _text(cell, value: str) -> None:
    """Store `value` as literal text even when it starts with '=' / '+' (else openpyxl makes it a
    formula and data_only reads it back as None)."""
    cell.value = value
    cell.data_type = "s"


def cabinet_counts(results: list[RowResult]) -> Counter:
    """Per-cabinet count of assigned signals, keyed by the EFFECTIVE 3-digit cabinet actually in the
    cell (a preserved human AE when present, else the computed one) so the Count matches the sheet."""
    def eff(r: RowResult) -> str:
        return r.iorow.ex_diag_cabinet.strip() or str(r.diag_cabinet or "")
    return Counter(eff(r) for r in results if eff(r))


def write_diagnosis_blocks(wb, blocks: list[DiagBlock], results: list[RowResult]):
    """Replace the DiagnosisBlocks sheet of `wb` with one row per block. Returns the worksheet."""
    for name in list(wb.sheetnames):
        if name.strip().lower() == DIAGBLOCKS_SHEET.lower():
            del wb[name]
    ws = wb.create_sheet(DIAGBLOCKS_SHEET)
    for c, h in enumerate(_HEADERS, 1):
        ws.cell(row=1, column=c, value=h)

    counts = cabinet_counts(results)
    for i, b in enumerate(blocks):
        r = 2 + i
        ws.cell(row=r, column=1, value=b.id_local)            # A ID_Local
        ws.cell(row=r, column=2, value=b.id_local)            # B ID_SWP (== ID_Local)
        _text(ws.cell(row=r, column=3), b.fu)                 # C Functional Unit (e.g. "=S1")
        _text(ws.cell(row=r, column=4), b.location)           # D Location ("+MC1.CC1" / "+SafetyDoors_1")
        _text(ws.cell(row=r, column=5), b.full_name)          # E FullName ("=S1+MC1.CC1") - staging reads
        ws.cell(row=r, column=6, value=b.template_type)       # F TemplateType (1 / 2)
        # G Notes - left blank
        ws.cell(row=r, column=8, value=int(counts.get(b.cabinet_text, 0)))   # H Count
    return ws
