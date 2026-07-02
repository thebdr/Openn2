"""The Files tab (GUI M5): a 3-section file tree (config / user-editable / output) on the left, a
read-only viewer on the right. A `.csv` / `.xlsx` opens in a Treeview grid (the xlsx gets a sheet picker);
a `.yaml`/`.json`/`.xml`/`.scl`/text file opens in a monospace text pane. Every viewer carries a path
strip + **Open externally** / **Open folder** buttons (`gui/excel`-free; `gui/extedit`), so editing happens
in the OS app while PL4 keeps its byte-stable codec the only writer (decision #3: view-only first). The
Tk-free scan/dispatch/read logic lives in `gui/files_view.py` (tested); this is the view.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from pipeline4.gui import extedit, files_view, theme


class FilesPanel(ttk.Frame):
    def __init__(self, parent, sections=None, on_status=lambda *_a: None, mode="dark"):
        super().__init__(parent)
        self.sections = sections or []
        self.on_status = on_status
        self._mode = mode
        self._paths: dict = {}            # tree item id -> absolute file path
        self._cur: str | None = None      # the file currently shown (re-themed in place)
        self._textw: tk.Text | None = None

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tvs = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tvs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tvs.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        ttk.Button(left, text="Refresh", command=self.refresh).pack(side="bottom", fill="x")
        panes.add(left, weight=1)

        self.editor = ttk.Frame(panes)
        panes.add(self.editor, weight=4)
        self._placeholder("Select a file from the tree.")
        self.refresh()

    # --- the tree ------------------------------------------------------------------------------- #
    def set_sections(self, sections) -> None:
        self.sections = sections
        self.refresh()

    def refresh(self) -> None:
        """(Re)build the section tree from `self.sections` (`{title, roots, include, exclude}` dicts -
        the compiled files_tab config). A section with no matching file shows '(empty)'. Called on
        construction, after each phase run, and on a project switch."""
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        for section in self.sections:
            node = self.tree.insert("", "end", text=section["title"], open=True)
            count = 0
            for root in section.get("roots", ()):
                for child in files_view.populate(root, section.get("include", ()), section.get("exclude", ())):
                    count += self._insert(node, child)
            if count == 0 and section.get("roots"):
                self.tree.insert(node, "end", text="(empty)")

    def _insert(self, parent, node) -> int:
        """Insert one files_view node (and its children) under `parent`; returns the count of FILE nodes
        added (so an all-empty branch can be reported)."""
        item = self.tree.insert(parent, "end", text=node["name"], open=False)
        if node["is_dir"]:
            files = 0
            for child in node["children"]:
                files += self._insert(item, child)
            return files
        self._paths[item] = node["path"]
        return 1

    def _on_select(self, _event) -> None:
        sel = self.tree.selection()
        path = self._paths.get(sel[0]) if sel else None
        if path:
            self._load(path)

    # --- dispatch + viewers --------------------------------------------------------------------- #
    def _load(self, path: str) -> None:
        self._cur = path
        kind = files_view.viewer_kind(path)
        try:
            if kind == "csv":
                self._show_csv(path)
            elif kind == "xlsx":
                self._show_xlsx(path)
            elif kind == "text":
                self._show_text(path)
            else:                                     # visible but no in-app viewer: still openable
                self._clear_editor()
                self._header(path)
                ttk.Label(self.editor, padding=12,
                          text=f"{os.path.basename(path)}: no in-app preview - use Open externally.").pack(anchor="nw")
        except Exception as error:  # noqa: BLE001  - a broken file must not take the tab down
            self._placeholder(f"could not open {os.path.basename(path)}: {error}")

    def _clear_editor(self) -> None:
        self._textw = None
        for w in self.editor.winfo_children():
            w.destroy()

    def _placeholder(self, text: str) -> None:
        self._clear_editor()
        ttk.Label(self.editor, text=text, padding=12).pack(anchor="nw")

    def _header(self, path: str) -> None:
        """The path strip + Open externally / Open folder buttons at the top of the editor pane."""
        entry = ttk.Entry(self.editor)
        entry.insert(0, os.path.abspath(path))
        entry.configure(state="readonly")
        entry.pack(side="top", fill="x", padx=6, pady=(6, 2))
        entry.xview_moveto(1.0)                       # show the tail (the filename)
        bar = ttk.Frame(self.editor)
        bar.pack(side="top", fill="x", padx=6, pady=(0, 4))
        ttk.Button(bar, text="Open externally",
                   command=lambda: self.on_status(extedit.open_external(path)[1])).pack(side="left")
        ttk.Button(bar, text="Open folder",
                   command=lambda: self.on_status(extedit.reveal(path)[1])).pack(side="left", padx=6)

    def _grid(self, rows) -> None:
        """A read-only Treeview grid for `rows` (row 0 = headers); ragged rows are padded."""
        frame = ttk.Frame(self.editor)
        frame.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        if not rows:
            ttk.Label(frame, text="(empty)", padding=8).pack(anchor="nw")
            return
        ncols = max(len(r) for r in rows)
        cols = [f"c{i}" for i in range(ncols)]
        header = rows[0]
        grid = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for i, c in enumerate(cols):
            label = str(header[i]) if i < len(header) else ""
            grid.heading(c, text=label)
            grid.column(c, width=max(60, min(360, 9 * len(label) + 30)), anchor="w", stretch=False)
        for row in rows[1:]:
            grid.insert("", "end", values=[row[i] if i < len(row) else "" for i in range(ncols)])
        vsb = ttk.Scrollbar(frame, orient="vertical", command=grid.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=grid.xview)
        grid.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        grid.pack(side="left", fill="both", expand=True)

    def _show_csv(self, path: str) -> None:
        self._clear_editor()
        self._header(path)
        self._grid(files_view.read_csv_rows(path))

    def _show_xlsx(self, path: str) -> None:
        self._clear_editor()
        self._header(path)
        names, _rows = files_view.read_xlsx(path)
        sel = ttk.Frame(self.editor)
        sel.pack(side="top", fill="x", padx=6)
        ttk.Label(sel, text="Sheet:").pack(side="left")
        box = ttk.Combobox(sel, values=names, state="readonly", width=28)
        box.pack(side="left", padx=(4, 12))
        holder = ttk.Frame(self.editor)
        holder.pack(side="top", fill="both", expand=True, padx=6, pady=(4, 6))

        def show(name):
            for w in holder.winfo_children():
                w.destroy()
            _n, rows = files_view.read_xlsx(path, name)
            grid = _ReadonlyGrid(holder, rows)
            grid.pack(side="top", fill="both", expand=True)

        box.bind("<<ComboboxSelected>>", lambda _e: show(box.get()))
        if names:
            box.set(names[0])
            show(names[0])

    def _show_text(self, path: str) -> None:
        self._clear_editor()
        self._header(path)
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            content = handle.read(400_000)            # cap a huge file so the pane stays responsive
        frame = ttk.Frame(self.editor)
        frame.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        text = tk.Text(frame, wrap="none", relief="flat", borderwidth=0,
                       background=theme.bg_for(self._mode), foreground=theme.fg_for(self._mode),
                       insertbackground=theme.fg_for(self._mode), font=theme.MONO_FONT)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        text.insert("1.0", content)
        text.configure(state="disabled")
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)
        self._textw = text

    def set_theme(self, mode: str) -> None:
        """Re-theme the panel for a light/dark switch. The ttk widgets follow the token styles; only the
        classic-tk text viewer needs its bg/fg set - reconfigure it live if one is shown."""
        self._mode = mode
        if self._textw is not None and self._textw.winfo_exists():
            self._textw.configure(background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                                  insertbackground=theme.fg_for(mode))


class _ReadonlyGrid(ttk.Frame):
    """A scrollable read-only Treeview grid (row 0 = headers) - the xlsx sheet body."""

    def __init__(self, parent, rows):
        super().__init__(parent)
        if not rows:
            ttk.Label(self, text="(empty sheet)", padding=8).pack(anchor="nw")
            return
        ncols = max(len(r) for r in rows)
        cols = [f"c{i}" for i in range(ncols)]
        header = rows[0]
        grid = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for i, c in enumerate(cols):
            label = str(header[i]) if i < len(header) else ""
            grid.heading(c, text=label)
            grid.column(c, width=max(60, min(360, 9 * len(label) + 30)), anchor="w", stretch=False)
        for row in rows[1:]:
            grid.insert("", "end", values=[row[i] if i < len(row) else "" for i in range(ncols)])
        vsb = ttk.Scrollbar(self, orient="vertical", command=grid.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=grid.xview)
        grid.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        grid.pack(side="left", fill="both", expand=True)
