#!/usr/bin/env python3
"""editor.py - in-GUI file editor for the Pipeline2 window.

A reusable `FileBrowser` (left: a tree of config + output files; right: a
`FileEditor`) for viewing/editing the pipeline's files without leaving the GUI:

  * .csv             -> spreadsheet grid (tksheet): in-cell edit, multi-select,
                        copy/paste, undo, right-click insert/delete row & column.
                        Read with delimiter sniffing, saved comma-delimited.
  * .xlsx / .xlsm    -> a sheet selector + the same grid, per sheet (values and
                        formula strings; openpyxl round-trips untouched cells).
  * everything else  -> a plain text editor (.db / .json / .txt / .scl / ...).

This is the base for later workflow-specific tooling (the user will expand it).
tksheet is a hard dependency here; if it is missing the grid degrades to text.
"""
from __future__ import annotations
import csv
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import openpyxl

try:
    from tksheet import Sheet
    _HAVE_TKSHEET = True
except ImportError:  # pragma: no cover - tksheet is expected to be installed
    _HAVE_TKSHEET = False

EDITABLE_EXT = {".csv", ".xlsx", ".xlsm", ".db", ".json", ".txt", ".scl", ".md", ".log"}
GRID_EXT = {".csv", ".xlsx", ".xlsm"}


def _col_letters(n: int) -> list:
    """Excel-style column headers: A, B, ... Z, AA, AB, ..."""
    out = []
    for i in range(max(n, 1)):
        s, x = "", i
        while True:
            s = chr(ord("A") + x % 26) + s
            x = x // 26 - 1
            if x < 0:
                break
        out.append(s)
    return out


def _sniff_delim(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return ";" if first.count(";") > first.count(",") else ","


def _read_csv_grid(path: str) -> list:
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    rows = list(csv.reader(text.splitlines(), delimiter=_sniff_delim(text)))
    width = max((len(r) for r in rows), default=1)
    return [r + [""] * (width - len(r)) for r in rows]


def _write_csv_grid(path: str, data: list) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")  # comma, minimal quoting
        for row in data:
            w.writerow(["" if c is None else c for c in row])


def _read_xlsx_grid(path: str, sheet: str) -> list:
    wb = openpyxl.load_workbook(path)  # keep formulas (round-trip untouched cells)
    ws = wb[sheet]
    data = [["" if v is None else v for v in row] for row in ws.iter_rows(values_only=True)]
    wb.close()
    width = max((len(r) for r in data), default=1)
    return [list(r) + [""] * (width - len(r)) for r in data]


def _write_xlsx_grid(path: str, sheet: str, data: list) -> None:
    wb = openpyxl.load_workbook(path)
    ws = wb[sheet]
    old_rows, old_cols = ws.max_row, ws.max_column
    for ri, row in enumerate(data, start=1):
        for ci, val in enumerate(row, start=1):
            ws.cell(row=ri, column=ci).value = (None if val == "" else val)
    new_rows = len(data)
    new_cols = max((len(r) for r in data), default=0)
    for r in range(1, old_rows + 1):       # blank cells beyond the new extent
        for c in range(1, old_cols + 1):
            if r > new_rows or c > new_cols:
                ws.cell(row=r, column=c).value = None
    wb.save(path)


class FileEditor(ttk.Frame):
    """Opens one file: a tksheet grid for csv/xlsx, a Text widget otherwise."""

    def __init__(self, parent, on_status=None):
        super().__init__(parent)
        self._on_status = on_status or (lambda msg: None)
        self.path = None
        self.mode = None          # "csv" | "xlsx" | "text"
        self.sheet_name = None
        self._grid = None
        self._text = None

        bar = ttk.Frame(self, padding=(4, 4))
        bar.pack(side="top", fill="x")
        self._path_var = tk.StringVar(value="(no file open)")
        ttk.Label(bar, textvariable=self._path_var, anchor="w").pack(side="left", fill="x", expand=True)
        self._sheet_var = tk.StringVar()
        self._sheet_combo = ttk.Combobox(bar, textvariable=self._sheet_var, width=22, state="readonly")
        self._sheet_combo.bind("<<ComboboxSelected>>", lambda e: self._load_sheet())
        self._save_btn = ttk.Button(bar, text="Save", command=self.save, state="disabled")
        self._reload_btn = ttk.Button(bar, text="Reload", command=self.reload, state="disabled")
        self._reload_btn.pack(side="right", padx=2)
        self._save_btn.pack(side="right", padx=2)
        # sheet combo is packed only for spreadsheets (see _show_sheet_combo)

        self._body = ttk.Frame(self)
        self._body.pack(side="top", fill="both", expand=True)

    # ---- public ---- #
    def open(self, path: str):
        if not path or not os.path.isfile(path):
            return
        self.path = path
        self._path_var.set(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            self.mode = "xlsx"
            wb = openpyxl.load_workbook(path, read_only=True)
            names = wb.sheetnames
            wb.close()
            self._sheet_combo.configure(values=names)
            self._sheet_var.set(names[0] if names else "")
            self._show_sheet_combo(True)
            self._load_sheet()
        elif ext == ".csv":
            self.mode = "csv"
            self._show_sheet_combo(False)
            self._show_grid(_read_csv_grid(path))
        else:
            self.mode = "text"
            self._show_sheet_combo(False)
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                self._show_text(f.read())
        self._save_btn.configure(state="normal")
        self._reload_btn.configure(state="normal")
        self._status(f"opened {os.path.basename(path)}")

    def reload(self):
        if self.path:
            self.open(self.path)

    def save(self):
        if not self.path:
            return
        try:
            if self.mode == "csv":
                _write_csv_grid(self.path, self._grid.get_sheet_data())
            elif self.mode == "xlsx":
                _write_xlsx_grid(self.path, self.sheet_name, self._grid.get_sheet_data())
            else:
                text = self._text.get("1.0", "end-1c")
                with open(self.path, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Save failed", f"{self.path}\n\n{e}")
            return
        self._status(f"saved {os.path.basename(self.path)}")

    # ---- internals ---- #
    def _status(self, msg):
        self._on_status(msg)

    def _show_sheet_combo(self, show: bool):
        if show:
            self._sheet_combo.pack(side="right", padx=6)
        else:
            self._sheet_combo.pack_forget()

    def _load_sheet(self):
        if self.mode != "xlsx":
            return
        self.sheet_name = self._sheet_var.get()
        self._show_grid(_read_xlsx_grid(self.path, self.sheet_name))

    def _clear_body(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._grid = None
        self._text = None

    def _show_grid(self, data: list):
        self._clear_body()
        ncols = max((len(r) for r in data), default=1)
        if _HAVE_TKSHEET:
            self._grid = Sheet(self._body, data=data, headers=_col_letters(ncols))
            self._grid.enable_bindings()  # edit, select, copy/paste, undo, rc menu
            self._grid.pack(fill="both", expand=True)
        else:  # graceful fallback: tab-joined text
            self._show_text("\n".join("\t".join(str(c) for c in r) for r in data))

    def _show_text(self, content: str):
        self._clear_body()
        self._text = tk.Text(self._body, wrap="none", font=("Consolas", 10), undo=True)
        ys = ttk.Scrollbar(self._body, orient="vertical", command=self._text.yview)
        xs = ttk.Scrollbar(self._body, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self._text.pack(side="left", fill="both", expand=True)
        self._text.insert("1.0", content)


class FileBrowser(ttk.Frame):
    """A file tree (config + outputs) beside a FileEditor. `roots` is a list of
    (label, path) where path is a folder (walked) or a single file."""

    def __init__(self, parent, roots, on_status=None):
        super().__init__(parent)
        self._roots = [(lbl, p) for lbl, p in roots if p]
        self._paths = {}  # tree item id -> file path

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        btns = ttk.Frame(left, padding=(2, 2))
        btns.pack(side="top", fill="x")
        ttk.Button(btns, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(btns, text="Open…", command=self._open_dialog).pack(side="left", padx=2)
        self._tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tys = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tys.set)
        tys.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        pane.add(left, weight=1)

        right = ttk.Frame(pane)
        self.editor = FileEditor(right, on_status=on_status)
        self.editor.pack(fill="both", expand=True)
        pane.add(right, weight=4)

        self.refresh()

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        self._paths.clear()
        for label, path in self._roots:
            node = self._tree.insert("", "end", text=label, open=True)
            if os.path.isfile(path):
                self._add_file(node, path)
            elif os.path.isdir(path):
                self._add_dir(node, path)

    def _add_dir(self, parent, folder: str):
        try:
            entries = sorted(os.listdir(folder), key=lambda s: s.lower())
        except OSError:
            return
        # subfolders first, then files
        for name in entries:
            full = os.path.join(folder, name)
            if os.path.isdir(full) and name not in ("__pycache__",):
                child = self._tree.insert(parent, "end", text=name + "/", open=False)
                self._add_dir(child, full)
        for name in entries:
            full = os.path.join(folder, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in EDITABLE_EXT:
                self._add_file(parent, full)

    def _add_file(self, parent, path: str):
        item = self._tree.insert(parent, "end", text=os.path.basename(path))
        self._paths[item] = path

    def _on_select(self, _event):
        sel = self._tree.selection()
        if sel and sel[0] in self._paths:
            self.editor.open(self._paths[sel[0]])

    def _open_dialog(self):
        p = filedialog.askopenfilename(title="Open file")
        if p:
            self.editor.open(p)
