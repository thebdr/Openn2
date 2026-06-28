"""The Database Explorer tab (GUI M3) - a SQL console over the SSOT.

A schema sidebar (the tables + columns), a SQL editor, and a results grid. On open / Refresh it loads
`Database/` into an in-memory SQLite DB (`dbquery.build_memory_db`) and runs SQL against it (read-only - an
in-memory copy; the CSVs are never touched). Sample queries (cross-table JOINs + `json_extract`) seed the
editor for discoverability; double-click a table in the sidebar to `SELECT * FROM` it. The query engine is
`dbquery` (Tk-free, tested); this is the Tk view.
"""
from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk

from pipeline4.core import config
from pipeline4.gui import dbquery

_RESULT_CAP = 2000          # max result rows rendered into the grid


class DatabaseExplorer(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = None
        self._schema: dict = {}

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # --- left: the schema sidebar --- #
        left = ttk.Frame(panes)
        ttk.Label(left, text="Tables").pack(side="top", anchor="w", padx=4, pady=(4, 0))
        self.schema = ttk.Treeview(left, show="tree", selectmode="browse")
        self.schema.pack(side="left", fill="both", expand=True)
        sbar = ttk.Scrollbar(left, orient="vertical", command=self.schema.yview)
        self.schema.configure(yscrollcommand=sbar.set)
        sbar.pack(side="right", fill="y")
        self.schema.bind("<Double-1>", self._on_schema_double)
        panes.add(left, weight=1)

        # --- right: toolbar + SQL editor + results --- #
        right = ttk.Frame(panes)
        bar = ttk.Frame(right)
        bar.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Button(bar, text="Run  (Ctrl+Enter)", command=self.run).pack(side="left", padx=2)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        ttk.Label(bar, text="Samples:").pack(side="left", padx=(10, 2))
        self._samples = ttk.Combobox(bar, width=34, state="readonly",
                                     values=[name for name, _sql in dbquery.SAMPLE_QUERIES])
        self._samples.pack(side="left", padx=2)
        self._samples.bind("<<ComboboxSelected>>", self._on_sample)
        self._status = ttk.Label(bar, text="")
        self._status.pack(side="right", padx=4)

        self.editor = tk.Text(right, height=5, wrap="none")
        self.editor.pack(side="top", fill="x", padx=4)
        self.editor.bind("<Control-Return>", lambda _e: (self.run(), "break")[1])
        self.editor.insert("1.0", "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

        rframe = ttk.Frame(right)
        rframe.pack(side="top", fill="both", expand=True, padx=4, pady=(4, 4))
        self.results = ttk.Treeview(rframe, show="headings", selectmode="browse")
        rvsb = ttk.Scrollbar(rframe, orient="vertical", command=self.results.yview)
        rhsb = ttk.Scrollbar(rframe, orient="horizontal", command=self.results.xview)
        self.results.configure(yscrollcommand=rvsb.set, xscrollcommand=rhsb.set)
        rvsb.pack(side="right", fill="y")
        rhsb.pack(side="bottom", fill="x")
        self.results.pack(side="left", fill="both", expand=True)
        panes.add(right, weight=4)

        self.refresh()

    def refresh(self) -> None:
        """(Re)load Database/ into a fresh in-memory SQLite DB and repopulate the schema sidebar."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._conn, self._schema = dbquery.build_memory_db(config.database_dir())
        except Exception as error:  # noqa: BLE001
            self._conn, self._schema = None, {}
            self._status.configure(text=f"load error: {error}")
        self.schema.delete(*self.schema.get_children())
        for table in sorted(self._schema):
            node = self.schema.insert("", "end", text=f"{table}  ({len(self._schema[table])})", open=False)
            for column in self._schema[table]:
                self.schema.insert(node, "end", text=column)
        self._status.configure(text=f"{len(self._schema)} table(s) loaded")

    def run(self) -> None:
        """Execute the editor's SQL against the in-memory DB and render the result grid."""
        if self._conn is None:
            self._status.configure(text="no database loaded - Refresh")
            return
        sql = self.editor.get("1.0", "end").strip()
        if not sql:
            return
        try:
            columns, rows = dbquery.run_query(self._conn, sql)
        except sqlite3.Error as error:
            self._status.configure(text=f"SQL error: {error}")
            return
        self.results.delete(*self.results.get_children())
        self.results["columns"] = columns
        for column in columns:
            self.results.heading(column, text=column)
            self.results.column(column, width=max(60, min(360, 9 * len(column) + 30)), anchor="w", stretch=False)
        for row in rows[:_RESULT_CAP]:
            self.results.insert("", "end", values=["" if v is None else str(v) for v in row])
        shown = min(len(rows), _RESULT_CAP)
        self._status.configure(text=f"{len(rows)} row(s)" + (f" (showing {shown})" if shown < len(rows) else ""))

    def _on_sample(self, _event) -> None:
        name = self._samples.get()
        sql = next((s for n, s in dbquery.SAMPLE_QUERIES if n == name), "")
        if sql:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", sql)
            self.run()

    def _on_schema_double(self, _event) -> None:
        item = self.schema.focus()
        if item and not self.schema.parent(item):                # a table node (no parent)
            table = self.schema.item(item, "text").split("  (")[0]
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", f'SELECT * FROM "{table}" LIMIT 100')
            self.run()
