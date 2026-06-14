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

import theme

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


def _read_xlsx_grid(path: str, sheet: str, data_only: bool = False) -> list:
    # data_only=False -> formula strings (round-trips untouched cells on save);
    # data_only=True  -> last cached computed values (view only).
    wb = openpyxl.load_workbook(path, data_only=data_only)
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
        self._pal = theme.LIGHT
        self._visible_cols = None  # None = all columns shown

        bar = ttk.Frame(self, padding=(4, 4))
        bar.pack(side="top", fill="x")
        self._path_var = tk.StringVar(value="(no file open)")
        ttk.Label(bar, textvariable=self._path_var, anchor="w").pack(side="left", fill="x", expand=True)

        # right-hand controls (packed right-to-left)
        self._reload_btn = ttk.Button(bar, text="Reload", command=self.reload, state="disabled")
        self._reload_btn.pack(side="right", padx=2)
        self._save_btn = ttk.Button(bar, text="Save", command=self.save, state="disabled")
        self._save_btn.pack(side="right", padx=2)
        self._columns_btn = ttk.Button(bar, text="Columns…", command=self._open_columns_filter, state="disabled")
        self._columns_btn.pack(side="right", padx=(8, 2))
        # xlsx-only controls (packed/forgotten in _show_xlsx_controls):
        self._show_values = tk.BooleanVar(value=False)
        self._values_chk = ttk.Checkbutton(bar, text="Show values", variable=self._show_values,
                                            command=self._load_sheet)
        self._sheet_var = tk.StringVar()
        self._sheet_combo = ttk.Combobox(bar, textvariable=self._sheet_var, width=22, state="readonly")
        self._sheet_combo.bind("<<ComboboxSelected>>", lambda e: self._load_sheet())

        self._body = ttk.Frame(self)
        self._body.pack(side="top", fill="both", expand=True)

    # ---- public ---- #
    def open(self, path: str):
        if not path or not os.path.isfile(path):
            return
        self.path = path
        self._path_var.set(path)
        self._visible_cols = None  # reset the column filter for the new file
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xlsm"):
            self.mode = "xlsx"
            wb = openpyxl.load_workbook(path, read_only=True)
            names = wb.sheetnames
            wb.close()
            self._sheet_combo.configure(values=names)
            self._sheet_var.set(names[0] if names else "")
            self._show_xlsx_controls(True)
            self._load_sheet()  # sets Save state (off while showing values)
        elif ext == ".csv":
            self.mode = "csv"
            self._show_xlsx_controls(False)
            self._show_grid(_read_csv_grid(path))
            self._save_btn.configure(state="normal")
        else:
            self.mode = "text"
            self._show_xlsx_controls(False)
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

    def _show_xlsx_controls(self, show: bool):
        for w in (self._values_chk, self._sheet_combo):
            if show:
                w.pack(side="right", padx=6)
            else:
                w.pack_forget()

    def _load_sheet(self):
        if self.mode != "xlsx":
            return
        self.sheet_name = self._sheet_var.get()
        values = self._show_values.get()
        self._visible_cols = None
        self._show_grid(_read_xlsx_grid(self.path, self.sheet_name, data_only=values))
        # showing computed values would clobber the formulas on save -> read-only
        self._save_btn.configure(state="disabled" if values else "normal")

    def _clear_body(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._grid = None
        self._text = None

    def _show_grid(self, data: list):
        self._clear_body()
        ncols = max((len(r) for r in data), default=1)
        if _HAVE_TKSHEET:
            self._grid = Sheet(self._body, data=data, headers=_col_letters(ncols),
                               font=theme.TABLE_FONT, header_font=theme.TABLE_HEADER_FONT)
            self._grid.enable_bindings()  # edit, select, copy/paste, undo, rc menu
            try:
                self._grid.change_theme(self._pal["sheet_theme"])
            except Exception:  # noqa: BLE001
                pass
            self._grid.pack(fill="both", expand=True)
            self._apply_zebra()
            self._columns_btn.configure(state="normal")
        else:  # graceful fallback when tksheet is unavailable
            self._columns_btn.configure(state="disabled")
            self._show_text("\n".join("\t".join(str(c) for c in r) for r in data))

    def _apply_zebra(self):
        """Steelblue + white text on even rows, light blue on odd rows."""
        if not self._grid:
            return
        n = len(self._grid.get_sheet_data())
        even = list(range(0, n, 2))
        odd = list(range(1, n, 2))
        try:
            if even:
                self._grid.highlight_rows(even, bg=theme.ZEBRA_A["bg"], fg=theme.ZEBRA_A["fg"], redraw=False)
            if odd:
                self._grid.highlight_rows(odd, bg=theme.ZEBRA_B["bg"], fg=theme.ZEBRA_B["fg"], redraw=True)
        except Exception:  # noqa: BLE001
            pass

    def _open_columns_filter(self):
        """Popup of per-column checkboxes (letter + first-row header) to show/hide."""
        if not self._grid:
            return
        data = self._grid.get_sheet_data()
        ncols = max((len(r) for r in data), default=0)
        if not ncols:
            return
        letters = _col_letters(ncols)
        headers = data[0] if data else []
        visible = set(self._visible_cols) if self._visible_cols is not None else set(range(ncols))

        top = tk.Toplevel(self)
        top.title("Show columns")
        top.transient(self.winfo_toplevel())
        frm = ttk.Frame(top, padding=8)
        frm.pack(fill="both", expand=True)
        vars_, per_col = [], 18
        for i in range(ncols):
            v = tk.BooleanVar(value=(i in visible))
            head = str(headers[i]).strip() if i < len(headers) else ""
            label = f"{letters[i]}  {head[:28]}" if head else letters[i]
            ttk.Checkbutton(frm, text=label, variable=v).grid(
                row=i % per_col, column=i // per_col, sticky="w", padx=6, pady=1)
            vars_.append(v)

        def apply():
            idx = [i for i, v in enumerate(vars_) if v.get()] or list(range(ncols))
            self._visible_cols = idx
            try:
                self._grid.display_columns(idx, all_columns_displayed=(len(idx) == ncols), redraw=True)
            except Exception:  # noqa: BLE001
                pass
            top.destroy()

        btns = ttk.Frame(top, padding=(8, 0, 8, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text="Apply", command=apply).pack(side="right")
        ttk.Button(btns, text="All", command=lambda: [v.set(True) for v in vars_]).pack(side="left")
        ttk.Button(btns, text="None", command=lambda: [v.set(False) for v in vars_]).pack(side="left", padx=4)

    def _show_text(self, content: str):
        self._clear_body()
        self._columns_btn.configure(state="disabled")
        self._text = tk.Text(self._body, wrap="none", font=("Consolas", 11), undo=True,
                             background=self._pal["field"], foreground=self._pal["fg"],
                             insertbackground=self._pal["fg"])
        ys = ttk.Scrollbar(self._body, orient="vertical", command=self._text.yview)
        xs = ttk.Scrollbar(self._body, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self._text.pack(side="left", fill="both", expand=True)
        self._text.insert("1.0", content)

    def apply_theme(self, pal: dict):
        self._pal = pal
        if self._text is not None:
            self._text.configure(background=pal["field"], foreground=pal["fg"], insertbackground=pal["fg"])
        if self._grid is not None:
            try:
                self._grid.change_theme(pal["sheet_theme"])
            except Exception:  # noqa: BLE001
                pass
            self._apply_zebra()  # re-assert zebra over the theme background


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

    def apply_theme(self, pal: dict):
        # the tree is a ttk widget (themed by the global style); forward to the editor
        self.editor.apply_theme(pal)
