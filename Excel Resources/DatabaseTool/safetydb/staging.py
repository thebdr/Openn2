"""Staging: read the I/O List into canonical rows.

Reads the source workbook with openpyxl (NOT read_only, so cell.font.strike is
available). Columns are read by POSITION (column letter) per the column_map -
the document has duplicate headers ("Description language 1" twice), so a
header-name map is unsafe; instead the header at each position is verified and a
mismatch is reported as a warning (catches reordered/inserted columns).

A row is excluded when any of its cells is struck through (predisposition, when
strike_handling = "exclude") or it carries a non-empty Skip Reason. Each kept
row gets its resolved signal-type record (from Script Type) and its source row.
"""
from __future__ import annotations
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from . import config


class StagedRow(dict):
    """Canonical row; attribute-ish access via keys, plus _source_row / _type."""


def _is_struck(ws, row_index: int, last_col: int) -> bool:
    for c in range(1, last_col + 1):
        cell = ws.cell(row=row_index, column=c)
        if cell.value not in (None, "") and cell.font and cell.font.strike:
            return True
    return False


def _norm(value):
    if value is None:
        return ""
    s = str(value).strip()
    return s


def _skip_reason_present(value) -> bool:
    """Skip Reason: empty or 0 means 'not skipped'."""
    s = _norm(value)
    return s not in ("", "0", "0.0")


def load_io_list(params: dict, signal_types: dict) -> tuple[list[StagedRow], list[str]]:
    spec = params["io_list"]
    header_row = spec["header_row"]
    colmap = config.load_column_map("IoList")
    warnings: list[str] = []

    wb = load_workbook(spec["path"], data_only=True)
    if spec["sheet"] not in wb.sheetnames:
        raise SystemExit(f"sheet '{spec['sheet']}' not in {spec['path']} (have {wb.sheetnames})")
    ws = wb[spec["sheet"]]
    last_col = ws.max_column

    # build position->canonical, verifying headers (collapse internal whitespace:
    # source headers wrap with embedded newlines, e.g. "Functional \nunit")
    def _hkey(s):
        return " ".join(_norm(s).split()).lower()

    fields = []  # (col_index, canonical)
    for m in colmap:
        ci = column_index_from_string(m["column"])
        actual = _norm(ws.cell(row=header_row, column=ci).value)
        # prefix match: real headers carry verbose suffixes, e.g.
        # "Description language 1 (1° part) (permanent part)"; binding is positional
        if not _hkey(actual).startswith(_hkey(m["expected_header"])):
            msg = (f"IoList column {m['column']}: header '{actual}' != expected "
                   f"'{m['expected_header']}' (mapping to {m['canonical']})")
            if m["required"]:
                raise SystemExit("ERROR " + msg)
            warnings.append(msg)
        fields.append((ci, m["canonical"]))

    rows: list[StagedRow] = []
    excluded_struck = excluded_skip = 0
    strike_exclude = str(params.get("strike_handling", "exclude")).lower() == "exclude"

    for r in range(header_row + 1, ws.max_row + 1):
        # an entirely empty row ends/skip
        if all(ws.cell(row=r, column=ci).value in (None, "") for ci, _ in fields):
            continue
        row = StagedRow((canon, _norm(ws.cell(row=r, column=ci).value)) for ci, canon in fields)
        row["_source_row"] = r

        if _skip_reason_present(row.get("skip_reason")):
            excluded_skip += 1
            continue
        if strike_exclude and _is_struck(ws, r, last_col):
            excluded_struck += 1
            continue

        row["_type"] = config.resolve_type(signal_types, row.get("script_type"))
        rows.append(row)

    wb.close()
    warnings.insert(0, f"IoList: {len(rows)} rows kept, {excluded_struck} struck, {excluded_skip} skip-reason")
    return rows, warnings
