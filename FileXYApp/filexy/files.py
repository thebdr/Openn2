"""File loading for the standalone viewer: CSV (delimiter-sniffed) and xlsx (openpyxl read-only,
lazily imported so the package works without it for CSV-only use). Returns (columns, rows) of
STRINGS - the grid's input shape. Caps guard against runaway sheets, not real data (projects of
10-20k rows are the normal case)."""
from __future__ import annotations

import csv
import os

MAX_ROWS, MAX_COLS = 200_000, 256


def read_csv(path: str) -> tuple:
    """(columns, rows) from a CSV - the delimiter sniffed from the first line (',' ';' '\\t' '|'),
    the first row taken as the header."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        sample = handle.readline()
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(handle, dialect)
        table = [row for _i, row in zip(range(MAX_ROWS + 1), reader)]
    if not table:
        return [], []
    return [str(c) for c in table[0][:MAX_COLS]], [r[:MAX_COLS] for r in table[1:]]


def xlsx_sheets(path: str) -> list:
    """The workbook's sheet names (openpyxl, read-only)."""
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(book.sheetnames)
    finally:
        book.close()


def read_xlsx(path: str, sheet: str | None = None) -> tuple:
    """(columns, rows) from one xlsx sheet (cached values, read-only; `sheet=None` = the first).
    The first row is the header; None cells become ''."""
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = book[sheet] if sheet else book[book.sheetnames[0]]
        table = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > MAX_ROWS:
                break
            table.append(["" if c is None else str(c) for c in row[:MAX_COLS]])
    finally:
        book.close()
    if not table:
        return [], []
    return table[0], table[1:]


def read_table(path: str, sheet: str | None = None) -> tuple:
    """(columns, rows) by extension: .csv or .xlsx/.xlsm."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return read_xlsx(path, sheet)
    return read_csv(path)
