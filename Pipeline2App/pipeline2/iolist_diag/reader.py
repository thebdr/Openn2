"""Read a fresh I/O List into IoRow records (spec §3 + §5).

Reads cell VALUES from a workbook opened with data_only=True (so Skip Reason - a formula in
AA - and the suggested-type formula come back as their cached values, and cell.font.strike is
available). Columns are resolved by canonical name via ColumnResolver - never a hardcoded
letter. The node-meta row (e.g. the 'NET SAFETY 50' line: id_node='50', no functional_unit /
address / script_type) is not a data row and is dropped; truly empty rows are dropped too.

Skip rules (§5) are NOT applied here - reader returns every data row (with its struck flag);
the orchestrator decides skip per row so the report can distinguish 'skipped' from 'unresolved'.
"""
from __future__ import annotations

from pipeline2.core import config
from pipeline2.iolist_diag.columns import ColumnResolver
from pipeline2.iolist_diag.models import IoRow


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _is_io_addr(addr: str) -> bool:
    a = addr.strip().upper()
    return a[:1] in ("I", "Q") and any(ch.isdigit() for ch in a)


def resolve_io_sheets(wb, params: dict, override=None) -> list[str]:
    """The I/O sheet names to process: `override` (CLI --sheets) wins, else io_list.sheet
    patterns (regex) matched against the workbook (config.resolve_sheets)."""
    patterns = config.as_sheet_list(override) if override else config.as_sheet_list(params["io_list"].get("sheet"))
    if not patterns:
        raise SystemExit(f"no I/O List sheet configured ({params['io_list'].get('path')})")
    sheets = config.resolve_sheets(patterns, wb.sheetnames)
    if not sheets:
        raise SystemExit(f"no sheet matched {patterns} (have {wb.sheetnames})")
    return sheets


def _struck(ws, row: int, last_col: int) -> bool:
    """True if any non-empty cell in the row is struck through (openpyxl cell.font.strike).
    Mirrors staging._is_struck - the project's 'deleted' marker."""
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row, column=c)
        if cell.value not in (None, "") and cell.font and cell.font.strike:
            return True
    return False


def _first_data_row(ws, cr: ColumnResolver, header_row: int) -> int:
    """The first row after the header that is a real data line (has a functional_unit, an I/O
    address, a script_type or an index) - skips the node-meta row(s) below the header."""
    for r in range(header_row + 1, ws.max_row + 1):
        if _looks_like_data(ws, cr, r):
            return r
    return header_row + 1


def _looks_like_data(ws, cr: ColumnResolver, r: int) -> bool:
    fu = _norm(cr.get(ws, r, "functional_unit"))
    addr = _norm(cr.get(ws, r, "bit"))
    st = _norm(cr.get(ws, r, "script_type"))
    idx = _norm(cr.get(ws, r, "index")) if "index" in cr else ""
    return bool(fu) or _is_io_addr(addr) or bool(st) or bool(idx)


def read_sheet(ws, sheet: str, cr: ColumnResolver, header_row: int = 1) -> list[IoRow]:
    """All data rows of one sheet -> [IoRow] (raw, stripped; struck flag set)."""
    last_col = ws.max_column
    rows: list[IoRow] = []
    start = _first_data_row(ws, cr, header_row)
    for r in range(start, ws.max_row + 1):
        if not _looks_like_data(ws, cr, r):
            continue                                   # blank / separator / stray meta row
        rows.append(IoRow(
            sheet=sheet,
            row=r,
            functional_unit=_norm(cr.get(ws, r, "functional_unit")),
            location=_norm(cr.get(ws, r, "location")),
            device=_norm(cr.get(ws, r, "device")),
            desc_l1=_norm(cr.get(ws, r, "desc_l1")),
            desc_l1b=_norm(cr.get(ws, r, "desc_l1b")),
            id_node=_norm(cr.get(ws, r, "id_node")),
            addr=_norm(cr.get(ws, r, "bit")),
            type_hw=_norm(cr.get(ws, r, "type_hw")),
            mnemonic=_norm(cr.get(ws, r, "mnemonic")),
            skip_reason=_norm(cr.get(ws, r, "skip_reason")),
            struck=_struck(ws, r, last_col),
            ex_script_type=_norm(cr.get(ws, r, "script_type")),
            ex_suggested=cr.get(ws, r, "suggested_type") if "suggested_type" in cr else None,
            ex_index=_norm(cr.get(ws, r, "index")) if "index" in cr else "",
            ex_diag_cabinet=_norm(cr.get(ws, r, "diag_cabinet")) if "diag_cabinet" in cr else "",
            ex_diag_bit=_norm(cr.get(ws, r, "diag_bit")) if "diag_bit" in cr else "",
        ))
    return rows


def read_iolist(wb_vals, params: dict, cr: ColumnResolver, override=None) -> tuple[list[IoRow], list[str]]:
    """Read every configured I/O sheet of `wb_vals` (a data_only=True workbook). Returns
    (rows, sheet_names); rows from all sheets are concatenated (each tagged with its sheet)."""
    header_row = int(params["io_list"].get("header_row", 1) or 1)
    sheets = resolve_io_sheets(wb_vals, params, override)
    rows: list[IoRow] = []
    for sheet in sheets:
        rows.extend(read_sheet(wb_vals[sheet], sheet, cr, header_row))
    return rows, sheets
