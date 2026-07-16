"""The Database Explorer tab (GUI M3) - a SQL console over the SSOT.

A schema sidebar (the tables + columns), a SQL editor, and a results grid. The SSOT loads into an
in-memory SQLite DB (`dbquery.build_memory_db`) LAZILY on the first tab visit, OFF the Tk thread (the
window never blocks on the load), and only when the `Database/` folder actually changed since the last
load (`dbquery.dir_stamp`) - so re-visiting the tab is free, and a phase run that rewrote the tables
triggers a fresh load on the next visit. Queries run read-only against the in-memory copy (the CSVs are
never touched). Sample queries (cross-table JOINs + `json_extract`) seed the editor for discoverability;
double-click a table in the sidebar to `SELECT * FROM` it. The query engine is `dbquery` (Tk-free,
tested); this is the Tk view. Results render in the shared `gui/datagrid` canvas grid (gridlines,
zebra rows, data-adapted column widths, small narrow font for long cells) - VIRTUAL, so only the
visible slice is ever drawn.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk

from pipeline5.core import config
from pipeline5.gui import datagrid
from pipeline5.gui import database_query as dbquery
from pipeline5.gui import theme

# ---------------------------------------------------------------------------
# SQL syntax-highlighting engine (pure Python, no Tk dependency)
# ---------------------------------------------------------------------------
# Single regex: comments > strings > numbers > identifiers (priority order).
_SQL_PATTERN = re.compile(
    r"(--[^\n]*)"             # group 1: single-line comment
    r"|(\/\*[\s\S]*?\*\/)"    # group 2: block comment
    r"|('(?:''|[^'])*')"      # group 3: string literal  ('it''s fine')
    r"|\b(\d+(?:\.\d+)?)\b"   # group 4: numeric literal
    r"|\b([A-Za-z_]\w*)\b",   # group 5: identifier -> keyword or function check
    re.IGNORECASE,
)

_KEYWORDS = frozenset({
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
    "CROSS", "NATURAL", "FULL", "ON", "AND", "OR", "NOT", "IN", "LIKE",
    "GLOB", "REGEXP", "IS", "NULL", "AS", "ORDER", "BY", "GROUP", "HAVING",
    "LIMIT", "OFFSET", "DISTINCT", "UNION", "ALL", "EXCEPT", "INTERSECT",
    "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "TABLE", "VIEW", "INDEX",
    "WITH", "RECURSIVE", "CASE", "WHEN", "THEN", "ELSE", "END", "EXISTS",
    "BETWEEN", "INTO", "VALUES", "SET", "ASC", "DESC", "PRAGMA", "USING",
    "OVER", "PARTITION", "WINDOW", "FILTER", "TRUE", "FALSE",
})

_FUNCTIONS = frozenset({
    "COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL", "GROUP_CONCAT",
    "COALESCE", "IFNULL", "NULLIF", "IIF", "TYPEOF", "CAST", "QUOTE",
    "JSON_EXTRACT", "JSON", "JSON_ARRAY", "JSON_OBJECT", "JSON_TYPE",
    "JSON_VALID", "JSON_PATCH", "JSON_REMOVE", "JSON_INSERT", "JSON_REPLACE",
    "LENGTH", "UPPER", "LOWER", "SUBSTR", "SUBSTRING", "TRIM", "LTRIM",
    "RTRIM", "REPLACE", "INSTR", "PRINTF", "FORMAT", "CHAR", "UNICODE",
    "HEX", "ZEROBLOB", "RANDOMBLOB", "ROUND", "ABS", "RANDOM", "LAST_INSERT_ROWID",
    "CHANGES", "TOTAL_CHANGES", "SQLITE_VERSION",
    "DATETIME", "DATE", "TIME", "JULIANDAY", "STRFTIME", "UNIXEPOCH",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "PERCENT_RANK", "CUME_DIST",
    "LEAD", "LAG", "FIRST_VALUE", "LAST_VALUE", "NTH_VALUE",
})

_RESULT_CAP = 2000          # max result rows handed to the grid


class DatabaseExplorer(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = None
        self._schema: dict = {}
        self._stamp: tuple | None = None      # the dir_stamp of the loaded copy (None = never loaded)
        self._loading = False

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
        ttk.Button(bar, text="Refresh", command=lambda: self.refresh(force=True)).pack(side="left", padx=2)
        ttk.Label(bar, text="Samples:").pack(side="left", padx=(10, 2))
        self._samples = ttk.Combobox(bar, width=34, state="readonly",
                                     values=[name for name, _sql in dbquery.SAMPLE_QUERIES])
        self._samples.pack(side="left", padx=2)
        self._samples.bind("<<ComboboxSelected>>", self._on_sample)
        self._status = ttk.Label(bar, text="")
        self._status.pack(side="right", padx=4)

        self._hl_job = None
        self.editor = tk.Text(right, height=5, wrap="none",
                              background=theme.DARK_BG, foreground=theme.DARK_FG,
                              insertbackground=theme.DARK_FG, font=theme.MONO_FONT)
        self.editor.pack(side="top", fill="x", padx=4)
        self.editor.bind("<Control-Return>", lambda _e: (self.run(), "break")[1])
        self.editor.bind("<Key>", self._schedule_highlight)
        self._configure_hl_tags("dark")
        self.editor.insert("1.0", "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        self._highlight()

        rframe = ttk.Frame(right)
        rframe.pack(side="top", fill="both", expand=True, padx=4, pady=(4, 4))
        self.results = datagrid.DataGrid(rframe, mode="dark")
        self.results.pack(fill="both", expand=True)
        panes.add(right, weight=4)

        # LAZY load: the tab maps when it is first selected; every re-visit re-checks the folder stamp
        # (a no-op while the SSOT is unchanged, a background reload after a phase run rewrote it).
        self.bind("<Map>", lambda _e: self.refresh())
        self._status.configure(text="database loads on first visit")

    def refresh(self, force: bool = False) -> None:
        """(Re)load Database/ into an in-memory SQLite DB OFF the Tk thread and repopulate the schema
        sidebar - skipped entirely when the folder stamp says the loaded copy is current (`force`
        rebuilds regardless - the toolbar Refresh button)."""
        if self._loading:
            return
        db_dir = config.database_dir()
        stamp = dbquery.dir_stamp(db_dir)
        if not force and self._conn is not None and stamp == self._stamp:
            return                                        # up to date - visiting the tab stays free
        self._loading = True
        self._status.configure(text="loading database…")
        result: dict = {}

        def _build():                                     # worker thread: file IO + sqlite fill only
            try:
                result["ok"] = dbquery.build_memory_db(db_dir)
            except Exception as error:  # noqa: BLE001
                result["err"] = error

        thread = threading.Thread(target=_build, daemon=True)
        thread.start()
        self._poll_build(thread, result, stamp)

    def _poll_build(self, thread, result, stamp) -> None:
        """Tk-side poll for the load worker (no cross-thread Tk calls)."""
        if thread.is_alive():
            self.after(60, lambda: self._poll_build(thread, result, stamp))
            return
        self._loading = False
        if "err" in result:
            self._conn, self._schema, self._stamp = None, {}, None
            self._status.configure(text=f"load error: {result['err']}")
        else:
            stale = self._conn
            self._conn, self._schema = result["ok"]
            self._stamp = stamp
            if stale is not None:
                try:
                    stale.close()
                except Exception:  # noqa: BLE001
                    pass
        self.schema.delete(*self.schema.get_children())
        for table in sorted(self._schema):
            node = self.schema.insert("", "end", text=f"{table}  ({len(self._schema[table])})", open=False)
            for column in self._schema[table]:
                self.schema.insert(node, "end", text=column)
        if "err" not in result:
            self._status.configure(text=f"{len(self._schema)} tables loaded")

    def run(self) -> None:
        """Execute the editor's SQL against the in-memory DB and render the result grid. The DataGrid
        renders VIRTUALLY (only the visible slice draws), so the whole capped result loads at once -
        the chunked Treeview fill this replaced is no longer needed."""
        if self._conn is None:
            self._status.configure(text="database still loading…" if self._loading
                                    else "no database loaded - Refresh")
            return
        sql = self.editor.get("1.0", "end").strip()
        if not sql:
            return
        try:
            columns, rows = dbquery.run_query(self._conn, sql)
        except sqlite3.Error as error:
            self._status.configure(text=f"SQL error: {error}")
            return
        shown = rows[:_RESULT_CAP]
        self.results.set_data(columns, [["" if v is None else str(v) for v in row] for row in shown])
        self._status.configure(text=f"{len(rows)} rows"
                                     + (f" (showing {len(shown)})" if len(shown) < len(rows) else ""))

    def _on_sample(self, _event) -> None:
        name = self._samples.get()
        sql = next((s for n, s in dbquery.SAMPLE_QUERIES if n == name), "")
        if sql:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", sql)
            self._highlight()
            self.run()

    def _on_schema_double(self, _event) -> None:
        item = self.schema.focus()
        if item and not self.schema.parent(item):                # a table node (no parent)
            table = self.schema.item(item, "text").split("  (")[0]
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", f'SELECT * FROM "{table}" LIMIT 100')
            self._highlight()
            self.run()

    # --- syntax highlighting ------------------------------------------------ #

    def _configure_hl_tags(self, mode: str) -> None:
        """Configure (or reconfigure) the five syntax-highlight tags for dark/light mode."""
        dark = mode == "dark"
        self.editor.tag_configure("sql_kw",  foreground="#74b9ff" if dark else "#0055cc")
        self.editor.tag_configure("sql_fn",  foreground="#a29bfe" if dark else "#7040a0")
        self.editor.tag_configure("sql_str", foreground="#55efc4" if dark else "#1a7e1a")
        self.editor.tag_configure("sql_num", foreground="#fdcb6e" if dark else "#c05c00")
        self.editor.tag_configure("sql_cmt", foreground="#b2bec3" if dark else "#6e7a8a",
                                  font=(theme.MONO_FONT[0], theme.MONO_FONT[1], "italic"))

    def _schedule_highlight(self, _event=None) -> None:
        """Debounced re-highlight: cancel any pending job and schedule a new one 60 ms out."""
        if self._hl_job:
            self.editor.after_cancel(self._hl_job)
        self._hl_job = self.editor.after(60, self._highlight)

    def _highlight(self) -> None:
        """Re-tokenise the editor content and apply syntax-highlight tags in one pass."""
        self._hl_job = None
        for tag in ("sql_kw", "sql_fn", "sql_str", "sql_num", "sql_cmt"):
            self.editor.tag_remove(tag, "1.0", "end")
        content = self.editor.get("1.0", "end-1c")
        if not content:
            return
        for m in _SQL_PATTERN.finditer(content):
            s, e = f"1.0+{m.start()}c", f"1.0+{m.end()}c"
            cmt1, cmt2, string, num, ident = m.groups()
            if cmt1 or cmt2:
                self.editor.tag_add("sql_cmt", s, e)
            elif string:
                self.editor.tag_add("sql_str", s, e)
            elif num is not None:
                self.editor.tag_add("sql_num", s, e)
            elif ident:
                word = ident.upper()
                if word in _KEYWORDS:
                    self.editor.tag_add("sql_kw", s, e)
                elif word in _FUNCTIONS:
                    self.editor.tag_add("sql_fn", s, e)

    def set_theme(self, mode: str) -> None:
        """Re-theme the editor + the results grid and reconfigure highlight tag colours."""
        self.editor.configure(background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                              insertbackground=theme.fg_for(mode))
        self._configure_hl_tags(mode)
        self._highlight()
        self.results.set_theme(mode)
