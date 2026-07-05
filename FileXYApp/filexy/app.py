"""The STANDALONE viewer window: Open a CSV/xlsx (sheet picker for workbooks), the full grid
feature set, a live quick-search box, Export of the current filtered/sorted view to CSV, and a
dark/light toggle. Everything data-related lives in the grid; this is just a thin frame."""
from __future__ import annotations

import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import files, theme
from .grid import DataGrid

_TITLE = "FileXY"
_FILETYPES = (("Tables", "*.csv *.xlsx *.xlsm"), ("CSV", "*.csv"),
              ("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*"))


class ViewerApp:
    def __init__(self, root, path: str | None = None):
        self.root = root
        self.mode = "dark"
        self.path: str | None = None
        root.title(_TITLE)
        root.geometry("1100x640")
        theme.apply(root, self.mode)

        bar = ttk.Frame(root)
        bar.pack(side="top", fill="x", padx=6, pady=5)
        ttk.Button(bar, text="Open…", command=self._open).pack(side="left")
        self._sheet = ttk.Combobox(bar, width=24, state="disabled", values=())
        self._sheet.pack(side="left", padx=(6, 0))
        self._sheet.bind("<<ComboboxSelected>>", lambda _e: self._load_sheet())
        ttk.Button(bar, text="Export view…", command=self._export).pack(side="left", padx=6)
        ttk.Button(bar, text="Theme", command=self._toggle_theme).pack(side="left")
        ttk.Label(bar, text="Search:").pack(side="left", padx=(14, 2))
        self._search = ttk.Entry(bar, width=28)
        self._search.pack(side="left")
        self._search.bind("<KeyRelease>", lambda _e: self.grid.quick_search(self._search.get()))

        self.grid = DataGrid(root, mode=self.mode, selectable=True)
        self.grid.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 2))

        self.status = ttk.Label(root, text="Open a .csv or .xlsx - or drop a path on the command line.",
                                anchor="w")
        self.status.pack(side="bottom", fill="x", padx=8, pady=(0, 4))
        if path:
            self._load(path)

    # --- files ------------------------------------------------------------------------------------ #
    def _open(self) -> None:
        chosen = filedialog.askopenfilename(parent=self.root, title="Open table",
                                            filetypes=_FILETYPES)
        if chosen:
            self._load(chosen)

    def _load(self, path: str) -> None:
        try:
            if os.path.splitext(path)[1].lower() in (".xlsx", ".xlsm"):
                sheets = files.xlsx_sheets(path)
                self._sheet.configure(state="readonly", values=sheets)
                self._sheet.set(sheets[0])
            else:
                self._sheet.configure(state="disabled", values=())
                self._sheet.set("")
            self.path = path
            self._load_sheet()
        except Exception as error:  # noqa: BLE001 - a bad file must not kill the window
            messagebox.showerror(_TITLE, f"Could not open {path}:\n{error}", parent=self.root)

    def _load_sheet(self) -> None:
        if not self.path:
            return
        columns, rows = files.read_table(self.path, self._sheet.get() or None)
        self._search.delete(0, "end")
        self.grid.set_data(columns, rows)
        self.root.title(f"{_TITLE} - {os.path.basename(self.path)}")
        self.status.configure(text=f"{os.path.basename(self.path)}"
                                   f"{(' · ' + self._sheet.get()) if self._sheet.get() else ''}"
                                   f" · {len(rows)} rows × {len(columns)} columns")

    def _export(self) -> None:
        """Write the CURRENT view (filters + sort applied, in display order) to a CSV."""
        if not self.grid._view:
            return
        chosen = filedialog.asksaveasfilename(parent=self.root, title="Export the current view",
                                              defaultextension=".csv", filetypes=(("CSV", "*.csv"),))
        if not chosen:
            return
        with open(chosen, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.grid._columns)
            for i in self.grid._view:
                writer.writerow(self.grid._rows[i])
        self.status.configure(text=f"exported {len(self.grid._view)} rows -> {chosen}")

    def _toggle_theme(self) -> None:
        self.mode = "light" if self.mode == "dark" else "dark"
        theme.apply(self.root, self.mode)
        self.grid.set_theme(self.mode)
