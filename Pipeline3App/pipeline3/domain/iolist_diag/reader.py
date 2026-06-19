"""Read the I/O sheet(s) into IoRow records.

Reads from a workbook loaded data_only=True, read_only=False (cached values for AA/AC + cell fonts
for strike). Detects the first data row (skips the node-meta line below the header - that line has
no functional_unit, no valid I/Q address, no script_type, no index), and carries the strike flag.
"""
from __future__ import annotations
import re

from pipeline3.core import config
from pipeline3.domain.iolist_diag.models import (
    IoRow, DIAGBLOCKS_SHEET, DIAGBLOCKS_LEGACY, UNRESOLVED_SHEET,
)

_GENERATED = {DIAGBLOCKS_SHEET.lower(), DIAGBLOCKS_LEGACY.lower(), UNRESOLVED_SHEET.lower()}

_IO_ADDR = re.compile(r"^[IQ]\s*\d", re.IGNORECASE)


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def resolve_io_sheets(wb, params, override=None) -> list:
    if override:
        pats = override
    else:
        pats = params.get("io_list", {}).get("sheet")
    names = config.resolve_sheets(pats, wb.sheetnames)
    if not names:
        raise ValueError(f"no I/O sheet matching {pats!r} in {wb.sheetnames}")
    return names


def _is_io_addr(s: str) -> bool:
    return bool(_IO_ADDR.match(s.strip()))


def _looks_like_data(ws, cr, r: int) -> bool:
    if _s(cr.get(ws, r, "functional_unit")):
        return True
    bit = _s(cr.get(ws, r, "bit"))
    if bit and _is_io_addr(bit):
        return True
    if _s(cr.get(ws, r, "script_type")):
        return True
    if "index" in cr and _s(cr.get(ws, r, "index")):
        return True
    return False


def _first_data_row(ws, cr, header_row: int) -> int:
    for r in range(header_row + 1, ws.max_row + 1):
        if _looks_like_data(ws, cr, r):
            return r
    return header_row + 1


def _struck(ws, r: int, last_col: int) -> bool:
    for c in range(1, last_col + 1):
        cell = ws.cell(row=r, column=c)
        if cell.value not in (None, "") and cell.font and cell.font.strike:
            return True
    return False


def read_sheet(ws, sheet: str, cr, header_row: int = 1) -> list:
    rows = []
    last_col = ws.max_column
    start = _first_data_row(ws, cr, header_row)
    for r in range(start, ws.max_row + 1):
        if not _looks_like_data(ws, cr, r):
            continue
        rows.append(IoRow(
            sheet=sheet,
            row=r,
            functional_unit=_s(cr.get(ws, r, "functional_unit")),
            location=_s(cr.get(ws, r, "location")),
            device=_s(cr.get(ws, r, "device")),
            desc_l1=_s(cr.get(ws, r, "desc_l1")),
            desc_l1b=_s(cr.get(ws, r, "desc_l1b")),
            id_node=_s(cr.get(ws, r, "id_node")),
            addr=_s(cr.get(ws, r, "bit")),
            type_hw=_s(cr.get(ws, r, "type_hw")),
            mnemonic=_s(cr.get(ws, r, "mnemonic")),
            skip_reason_cell=_s(cr.get(ws, r, "skip_reason")),
            struck=_struck(ws, r, last_col),
            ex_script_type=_s(cr.get(ws, r, "script_type")),
            ex_suggested=cr.get(ws, r, "suggested_type"),
            ex_index=_s(cr.get(ws, r, "index")),
            ex_diag_cabinet=_s(cr.get(ws, r, "diag_cabinet")),
            ex_diag_bit=_s(cr.get(ws, r, "diag_bit")),
        ))
    return rows


def read_iolist(wb, params, cr, override=None) -> tuple:
    """Read every matching I/O sheet, concatenated (index/diag are global across all of them).
    Returns (rows, matched_sheet_names, skipped_sheet_names). `skipped` = workbook sheets that did
    not match the io_list.sheet pattern, excluding Pipeline3's own generated sheets."""
    names = resolve_io_sheets(wb, params, override)
    skipped = [n for n in wb.sheetnames if n not in names and n.strip().lower() not in _GENERATED]
    rows = []
    header_row = int(params.get("io_list", {}).get("header_row", 1) or 1)
    for name in names:
        rows.extend(read_sheet(wb[name], name, cr, header_row))
    return rows, names, skipped
