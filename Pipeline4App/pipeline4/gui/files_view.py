"""The Tk-free logic behind the Files tab (GUI M5): which files to show, which viewer a file gets, the
file-tree structure, and the read helpers (CSV + xlsx). The Tk view (`gui/files_panel.py`) renders the
tree these functions build and calls the readers; keeping the logic here makes it unit-testable without a
display. Clean-room port of the PL3 `gui/files.py` dispatch/scan, VIEW-ONLY (decision #3: a table edit
must go through the codec, so the first cut previews + opens externally, it does not write).
"""
from __future__ import annotations

import csv as _csv
import os

from pipeline4.core import config

# extension -> viewer kind. Objects/text share the read-only monospace viewer (the rich object editor is
# deferred with editing); a CSV / xlsx gets the read-only grid.
_GRID_EXT = (".csv",)
_XLSX_EXT = (".xlsx", ".xlsm", ".xls")
_TEXT_EXT = (".yaml", ".yml", ".json", ".xml", ".scl", ".db", ".txt", ".md", ".log")
_SHOW_EXT = _GRID_EXT + _XLSX_EXT + _TEXT_EXT

XLSX_MAX_ROWS, XLSX_MAX_COLS = 3000, 80   # cap a huge sheet so the preview stays responsive (PL3 parity)


def allowed(name: str) -> bool:
    """Show this file in the tree? Hides Excel lock files (`~$`), backups (`.bak_`), pyc/pycache, and any
    extension without a viewer."""
    low = name.lower()
    if low.startswith("~$") or low.endswith(".pyc") or ".bak_" in low or "__pycache__" in low:
        return False
    return low.endswith(_SHOW_EXT)


def viewer_kind(name: str) -> str | None:
    """The viewer a file gets by extension: 'csv' | 'xlsx' | 'text', or None when unsupported."""
    low = name.lower()
    if low.endswith(_GRID_EXT):
        return "csv"
    if low.endswith(_XLSX_EXT):
        return "xlsx"
    if low.endswith(_TEXT_EXT):
        return "text"
    return None


def _node(name, path, is_dir, children=None) -> dict:
    return {"name": name, "path": os.path.abspath(path), "is_dir": is_dir, "children": children or []}


def populate(root: str) -> list:
    """The tree nodes under `root` (a dir -> its allowed entries, recursive; a file -> a single node).
    Directories are listed first-sorted folders-then-files; a folder with no shown files is PRUNED, so the
    tree only shows branches that lead to a viewable file. Returns a list of node dicts (Tk-free)."""
    if not root or not os.path.exists(root):
        return []
    if os.path.isfile(root):
        return [_node(os.path.basename(root), root, False)] if allowed(os.path.basename(root)) else []
    try:
        entries = sorted(os.scandir(root), key=lambda e: (e.is_file(), e.name.lower()))
    except OSError:
        return []
    nodes = []
    for e in entries:
        if e.name.startswith(".") or e.name == "__pycache__":
            continue
        if e.is_dir():
            children = populate(e.path)
            if children:                                # prune empty branches
                nodes.append(_node(e.name + "/", e.path, True, children))
        elif allowed(e.name):
            nodes.append(_node(e.name, e.path, False))
    return nodes


def file_sections(params: dict) -> list:
    """The 3 Files-tree sections, each `(label, [root paths])`, resolved against the ACTIVE config/project:
    project configuration (the config_project tree), the user-editable inputs (the I/O List + C&E + the
    treatment registry), and the generated output (the SSOT Database + the BuilderData/ProjectDocumentation
    output tree)."""
    inputs = [p for p in (params.get("iolist_path"), params.get("matrix_path")) if p]
    uin = config.user_input_dir()
    if os.path.isdir(uin):
        inputs.append(uin)
    return [
        ("Project configuration", [config.config_project_dir()]),
        ("User editable files", inputs),
        ("Generated output", [config.database_dir(), config.output_root()]),
    ]


def sniff_delim(text: str) -> str:
    """The delimiter of a CSV's first non-empty line: ';' when it has more semicolons than commas, else
    ',' (the SSOT tables are comma; hand-authored config CSVs are sometimes semicolon)."""
    line = next((ln for ln in text.splitlines() if ln.strip()), "")
    return ";" if line.count(";") > line.count(",") else ","


def read_csv_rows(path: str) -> list:
    """A CSV file -> a list of string rows (delimiter sniffed). Read-only; cells stay raw text (JSON cells
    show as their JSON string, which is exactly what's on disk)."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    return list(_csv.reader(text.splitlines(), delimiter=sniff_delim(text)))


def read_xlsx(path: str, sheet: str | None = None):
    """(sheetnames, rows) for an xlsx/xlsm: the sheet names + the chosen sheet's cells as strings (cached
    values, read-only), capped to XLSX_MAX_ROWS x XLSX_MAX_COLS. `sheet=None` reads the first sheet."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        names = list(wb.sheetnames)
        if not names:
            return [], []
        name = sheet if sheet in names else names[0]
        rows = []
        for i, row in enumerate(wb[name].iter_rows(values_only=True)):
            if i >= XLSX_MAX_ROWS:
                break
            rows.append(["" if c is None else str(c) for c in row[:XLSX_MAX_COLS]])
        return names, rows
    finally:
        wb.close()
