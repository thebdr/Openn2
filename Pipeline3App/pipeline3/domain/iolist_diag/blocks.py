"""§9 (re)write the DiagnosisBlocks sheet.

ID_SWP == ID_Local (staging joins on ID_SWP). FU / Location / FullName are materialized AS TEXT
(data_type 's') so a leading '=' / '+' is not treated as a formula (staging reads them via
data_only). The sheet is cleared + recreated each time it is written; Type-1 rows first, then Type-2.
"""
from __future__ import annotations
from collections import defaultdict

from pipeline3.domain.iolist_diag.models import DIAGBLOCKS_SHEET, DIAGBLOCKS_LEGACY

HEADERS = ["ID_Local", "ID_SWP", "Functional Unit", "Location", "FullName",
           "TemplateType", "Notes", "Count"]


def _text(cell, value: str) -> None:
    cell.value = value if value is not None else ""
    cell.data_type = "s"


def cabinet_counts(results: list) -> dict:
    counts = defaultdict(int)
    for r in results:
        if r.diag_cabinet:
            counts[str(r.diag_cabinet)] += 1
    return counts


def write_diagnosis_blocks(wb, blocks: list, results: list):
    for name in list(wb.sheetnames):
        if name.strip().lower() in (DIAGBLOCKS_SHEET.lower(), DIAGBLOCKS_LEGACY.lower()):
            del wb[name]
    ws = wb.create_sheet(DIAGBLOCKS_SHEET)
    ws.append(HEADERS)
    counts = cabinet_counts(results)
    r = 2
    for b in blocks:
        ws.cell(r, 1, b.id_local)
        ws.cell(r, 2, b.id_local)              # ID_SWP == ID_Local
        _text(ws.cell(r, 3), b.fu)
        _text(ws.cell(r, 4), b.location)
        _text(ws.cell(r, 5), b.full_name)
        ws.cell(r, 6, b.template_type)
        ws.cell(r, 7, "")
        ws.cell(r, 8, counts.get(b.cabinet_text, 0))
        r += 1
    return ws
