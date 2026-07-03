"""The Findings panel (GUI M2) - a tab listing the SSOT findings with one-click treatments.

Rebuilt on the shared `DataGrid` (production-test feedback): zebra rows, data-adapted column widths
with the small narrow font for >64-char cells, mouse-resizable columns, and row MULTI-selection.
Reads the `validation_issues` table (the facts of the last run, persisted under `Database/`) joined to
the `error_management.csv` treatment registry; each row now also shows the log line's KEY CONTEXT -
the other-side location (`vs`), the bit/FLD identity, and the flattened `===`/`=/=` comparison (what
was different) - persisted by `finding.record`. Context columns that are empty across the whole view
are hidden. Filterable by phase + effective severity; rows are coloured by effective severity.
Right-click treats the WHOLE selection (fail/error/warn/clear; `skip`+`ignore` are GREYED for now -
UI only, re-enabled once the app reaches a stable version). The pure join/treat logic is in
`findings_view` (tested); this is the Tk view.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from pipeline4.core import config
from pipeline4.core.database import Database as DB
from pipeline4.core.finding import validation_issues_table
from pipeline4.core import treatments
from pipeline4.gui import findings_view, theme
from pipeline4.gui.datagrid import DataGrid

_BASE_COLUMNS = ("phase", "type", "severity", "effective", "treatment", "location")
_CONTEXT_COLUMNS = ("location2", "bit", "fld", "compared")   # hidden when empty across the view
_HEADERS = {"location2": "vs", "compared": "compared (=== / =/=)"}
_SEVERITIES = ("", "FAIL", "ERROR", "WARN", "INFO", "SKIP", "PASS")
_DISABLED_TREATMENTS = ("skip", "ignore")    # greyed for now (UI only) until the app is stable


def _load_issues() -> list:
    """The `validation_issues` rows from `Database/` ([] when absent / not yet produced)."""
    path = os.path.join(config.database_dir(), "validation_issues.csv")
    if not os.path.exists(path):
        return []
    try:
        database = DB([validation_issues_table()]).load(config.database_dir())
        return list(database["validation_issues"]) if "validation_issues" in database else []
    except Exception:  # noqa: BLE001 - a malformed registry/table must not take the panel down
        return []


class FindingsPanel(ttk.Frame):
    def __init__(self, parent, mode: str = "dark"):
        super().__init__(parent)
        self._mode = "dark" if mode == "dark" else "light"

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=4, pady=4)
        ttk.Label(bar, text="Phase:").pack(side="left", padx=(2, 2))
        self._phase = ttk.Combobox(bar, width=6, state="readonly", values=("",))
        self._phase.pack(side="left", padx=(0, 8))
        self._phase.bind("<<ComboboxSelected>>", lambda _e: self._render())
        ttk.Label(bar, text="Severity:").pack(side="left", padx=(2, 2))
        self._sev = ttk.Combobox(bar, width=7, state="readonly", values=_SEVERITIES)
        self._sev.pack(side="left", padx=(0, 8))
        self._sev.bind("<<ComboboxSelected>>", lambda _e: self._render())
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        self._count = ttk.Label(bar, text="0 findings")
        self._count.pack(side="right", padx=4)

        self.grid_view = DataGrid(self, mode=self._mode, selectable=True, on_context=self._popup)
        self.grid_view.pack(side="top", fill="both", expand=True)

        self.menu = tk.Menu(self, tearoff=0)
        for level in treatments.TREATMENTS:          # fail / error / warn / skip / ignore
            self.menu.add_command(label=f"Treat as {level.upper()}",
                                  command=lambda lv=level: self._treat(lv),
                                  state="disabled" if level in _DISABLED_TREATMENTS else "normal")
        self.menu.add_separator()
        self.menu.add_command(label="Clear treatment", command=lambda: self._treat(""))

        self._all: list = []
        self._shown: list = []                       # the filtered rows, index-aligned with the grid
        self.refresh()

    def refresh(self) -> None:
        """Reload validation_issues + the registry and re-render (keeping the current filters)."""
        self._all = findings_view.panel_rows(_load_issues(), treatments.load())
        phases_present = sorted({r["phase"] for r in self._all}, key=lambda p: (p == "", p))
        self._phase.configure(values=("",) + tuple(phases_present))
        self._render()

    def _render(self) -> None:
        rows = findings_view.filter_rows(self._all, self._phase.get(), self._sev.get())
        self._shown = rows
        # the context columns only appear when the view actually carries their data
        cols = list(_BASE_COLUMNS) + [c for c in _CONTEXT_COLUMNS if any(r[c] for r in rows)] + ["detail"]
        palette = theme.log_colors_for(self._mode)
        row_fg = [palette.get(r["effective"], ("",))[0] for r in rows]
        headers = [_HEADERS.get(c, c.title()) for c in cols]
        self.grid_view.set_data(headers, [[r[c] for c in cols] for r in rows], row_fg=row_fg)
        self._count.configure(text=f"{len(rows)} findings"
                              + (f" of {len(self._all)}" if len(rows) != len(self._all) else ""))

    def _popup(self, event, _selected) -> None:
        """The grid's context callback: the selection is already settled - show the treat menu."""
        self.menu.tk_popup(event.x_root, event.y_root)

    def _treat(self, level: str) -> None:
        """Treat the WHOLE selection at `level` (one registry write), then re-render."""
        rows = [self._shown[i] for i in self.grid_view.selection() if i < len(self._shown)]
        if not rows:
            return
        findings_view.apply_treatments(rows, level)
        self.refresh()

    def set_theme(self, mode: str) -> None:
        """Follow a light/dark toggle: re-skin the grid + re-render (the severity colours re-resolve)."""
        self._mode = "dark" if mode == "dark" else "light"
        self.grid_view.set_theme(self._mode)
        self._render()
