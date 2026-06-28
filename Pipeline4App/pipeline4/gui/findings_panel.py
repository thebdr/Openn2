"""The Findings panel (GUI M2) - a tab listing the SSOT findings with one-click treatments.

Reads the `validation_issues` table (the facts of the last run, persisted under `Database/`) joined to the
`error_management.csv` treatment registry, shows each finding's phase/type/default+EFFECTIVE severity/
location/detail, filterable by phase + effective severity. Right-click a row to treat it (fail/error/warn/
skip/ignore/clear) - writes the registry by `uid` and re-renders. `refresh()` reloads (the host calls it
after a phase run). The pure join/treat logic is in `findings_view` (tested); this is the Tk view.
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

_COLUMNS = (("phase", 60), ("type", 170), ("severity", 70), ("effective", 75),
            ("treatment", 80), ("location", 150), ("detail", 460))
_SEVERITIES = ("", "FAIL", "ERROR", "WARN", "INFO", "SKIP", "PASS")


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
    def __init__(self, parent):
        super().__init__(parent)
        self._rows: dict = {}                       # tree item id -> the display row

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

        cols = [c for c, _w in _COLUMNS]
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for col, width in _COLUMNS:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w", stretch=(col == "detail"))
        for level, (color, _bold) in theme.LOG_COLORS.items():
            self.tree.tag_configure(level, foreground=color)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.menu = tk.Menu(self, tearoff=0)
        for level in treatments.TREATMENTS:         # fail / error / warn / skip / ignore
            self.menu.add_command(label=f"Treat as {level.upper()}", command=lambda lv=level: self._treat(lv))
        self.menu.add_separator()
        self.menu.add_command(label="Clear treatment", command=lambda: self._treat(""))
        self.tree.bind("<Button-3>", self._popup)

        self._all: list = []
        self.refresh()

    def refresh(self) -> None:
        """Reload validation_issues + the registry and re-render (keeping the current filters)."""
        self._all = findings_view.panel_rows(_load_issues(), treatments.load())
        phases_present = sorted({r["phase"] for r in self._all}, key=lambda p: (p == "", p))
        self._phase.configure(values=("",) + tuple(phases_present))
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        rows = findings_view.filter_rows(self._all, self._phase.get(), self._sev.get())
        for r in rows:
            iid = self.tree.insert("", "end", tags=(r["effective"],), values=(
                r["phase"], r["type"], r["severity"], r["effective"], r["treatment"], r["location"], r["detail"]))
            self._rows[iid] = r
        self._count.configure(text=f"{len(rows)} findings" + (f" of {len(self._all)}" if len(rows) != len(self._all) else ""))

    def _popup(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def _treat(self, level: str) -> None:
        row = self._rows.get(self.tree.focus())
        if not row:
            return
        findings_view.apply_treatment(row["uid"], level, row)
        self.refresh()
