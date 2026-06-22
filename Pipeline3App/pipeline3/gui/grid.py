"""grid.py - decorate a tksheet `Sheet` with zebra striping + right-click column sort/filter.

All non-destructive (VIEW-only): sorting and filtering reorder/subset the DISPLAY via
`display_rows`, never the underlying data - so a Save of an edited CSV keeps the file's own row
order. Row 0 (the header row of our CSV/xlsx grids) is always kept pinned at the top. The header
right-click menu (tksheet `popup_menu_add_command(header_menu=True)`) gets: Sort ▲ / Sort ▼ /
Filter… / Clear. Re-stripes after every change so the zebra follows the visible rows.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

_STRIPE_DARK = "#2a2a2a"
_STRIPE_LIGHT = "#eef2f7"
_HEADERTINT_DARK = "#333333"
_HEADERTINT_LIGHT = "#dbe5f0"


def _key(v):
    """Sort key: numeric when the whole cell is a number, else case-folded text."""
    s = str(v).strip()
    try:
        return (0, float(s))
    except ValueError:
        return (1, s.lower())


class Grid:
    """Wraps a tksheet `Sheet`; adds zebra + header-menu sort/filter. `header_row` pins row 0."""

    def __init__(self, sheet, dark: bool, header_row: bool = True):
        self.s = sheet
        self.dark = dark
        self.header_row = header_row
        self.order = list(range(self._n()))
        self._add_menu()
        self.refresh()

    def _n(self) -> int:
        return len(self.s.get_sheet_data())

    def _body(self):
        return range(1, self._n()) if self.header_row else range(self._n())

    def _col(self) -> int:
        cols = self.s.get_selected_columns(return_tuple=True)
        return cols[0] if cols else 0

    def _head(self):
        return [0] if (self.header_row and self._n()) else []

    # ---- actions --------------------------------------------------------- #
    def sort(self, reverse: bool):
        c = self._col()
        vals = self.s.get_column_data(c)
        body = sorted(self._body(), key=lambda i: _key(vals[i] if i < len(vals) else ""), reverse=reverse)
        self.order = self._head() + body
        self.refresh()

    def clear(self):
        self.order = list(range(self._n()))
        self.refresh()

    def filter(self):
        c = self._col()
        vals = self.s.get_column_data(c)
        header = str(vals[0]) if (self.header_row and vals) else f"column {c + 1}"
        distinct = sorted({str(vals[i]) for i in self._body() if i < len(vals)}, key=_key)
        self._dialog(c, header, distinct)

    def _apply(self, c, pred):
        vals = self.s.get_column_data(c)
        body = [i for i in self._body() if pred(str(vals[i] if i < len(vals) else ""))]
        self.order = self._head() + body
        self.refresh()

    # ---- display + zebra ------------------------------------------------- #
    def refresh(self):
        self.s.display_rows(self.order, all_rows_displayed=False, reset_row_positions=True, redraw=False)
        self._zebra()
        self.s.redraw()

    def _zebra(self):
        self.s.dehighlight_all(redraw=False)
        if self._head():
            self.s.highlight_rows(self._head(),
                                  bg=_HEADERTINT_DARK if self.dark else _HEADERTINT_LIGHT, redraw=False)
        body = self.order[len(self._head()):]
        stripe = body[1::2]                       # every other VISIBLE body row
        if stripe:
            self.s.highlight_rows(stripe, bg=_STRIPE_DARK if self.dark else _STRIPE_LIGHT, redraw=False)

    def _add_menu(self):
        opts = dict(header_menu=True, table_menu=False, index_menu=False, empty_space_menu=False)
        self.s.popup_menu_add_command("Sort ▲ (this column)", lambda: self.sort(False), **opts)
        self.s.popup_menu_add_command("Sort ▼ (this column)", lambda: self.sort(True), **opts)
        self.s.popup_menu_add_command("Filter… (this column)", self.filter, **opts)
        self.s.popup_menu_add_command("Clear sort/filter", lambda: self.clear(), **opts)

    # ---- the filter dialog ----------------------------------------------- #
    def _dialog(self, c, header, distinct):
        top = tk.Toplevel(self.s)
        top.title(f"Filter: {header}")
        top.transient(self.s.winfo_toplevel())
        ttk.Label(top, text=f"Filter '{header}'", padding=(8, 6)).pack(anchor="w")
        row = ttk.Frame(top, padding=(8, 0))
        row.pack(fill="x")
        ttk.Label(row, text="contains:").pack(side="left")
        contains = tk.StringVar()
        ttk.Entry(row, textvariable=contains, width=24).pack(side="left", padx=4)
        ttk.Label(top, text="or pick values (none = all):", padding=(8, 4)).pack(anchor="w")
        lb = tk.Listbox(top, selectmode="extended", height=min(12, max(3, len(distinct))), width=40,
                        exportselection=False)
        for v in distinct:
            lb.insert("end", v)
        lb.pack(fill="both", expand=True, padx=8)
        btns = ttk.Frame(top, padding=8)
        btns.pack(fill="x")

        def apply_():
            text = contains.get().strip().lower()
            picks = {distinct[i] for i in lb.curselection()}
            if text:
                pred = (lambda v, t=text: t in v.lower())
            elif picks:
                pred = (lambda v, p=picks: v in p)
            else:
                top.destroy()
                return self.clear()
            self._apply(c, pred)
            top.destroy()

        ttk.Button(btns, text="Apply", command=apply_).pack(side="right")
        ttk.Button(btns, text="Cancel", command=top.destroy).pack(side="right", padx=6)
        ttk.Button(btns, text="Clear", command=lambda: (top.destroy(), self.clear())).pack(side="left")
        top.bind("<Return>", lambda _e: apply_())
        top.bind("<Escape>", lambda _e: top.destroy())
        lb.focus_set()


def decorate(sheet, dark: bool, header_row: bool = True) -> Grid:
    """Attach zebra + right-click sort/filter to `sheet`; returns the Grid (held by the caller)."""
    return Grid(sheet, dark, header_row=header_row)
