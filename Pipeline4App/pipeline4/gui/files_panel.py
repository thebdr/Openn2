"""The Files tab (GUI M5 + the refresh): a config-driven file tree on the left, a viewer on the right.
A `.csv` / `.xlsx` opens in the shared read-only DataGrid (the xlsx gets a sheet picker); a
`.yaml`/`.json` gets highlighting + the Text ⇄ Object-explorer toggle; every text-based file opens in
an EDITABLE monospace pane (Save/Ctrl+S writes atomically with the original BOM/newline style; a
dirty pane guards against silent discard; an over-cap file falls back to read-only). Every viewer
carries a path strip + **Open externally** / **Open folder** buttons (`gui/extedit`). Table edits
still go through the codec (the grids stay read-only). The Tk-free scan/filter/read/write logic
lives in `gui/files_view.py` (tested); this is the view.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from pipeline4.gui import datagrid, extedit, files_view, highlight, object_editor, theme


class FilesPanel(ttk.Frame):
    def __init__(self, parent, sections=None, on_status=lambda *_a: None, mode="dark"):
        super().__init__(parent)
        self.sections = sections or []
        self.on_status = on_status
        self._mode = mode
        self._paths: dict = {}            # tree item id -> absolute file path
        self._cur: str | None = None      # the file currently shown (re-themed in place)
        self._textw: tk.Text | None = None
        self._text_editable = False       # the shown text pane accepts edits (drives the dirty guard)
        self._csv_dirty = False           # the shown CSV grid carries unsaved cell edits
        self._reselecting = False         # ignore the selection event our own dirty-guard rollback fires
        self._obj_mode = False            # the yaml/json Text ⇄ Object toggle (remembered per session)

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        # Refresh packs FIRST as a slim full-width strip above the tree (packed after the tree, the
        # packer squeezed it into a full-height side column). Matches the Database Explorer's toolbar.
        ttk.Button(left, text="Refresh", command=self.refresh).pack(side="top", fill="x", pady=(0, 2))
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tvs = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tvs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tvs.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
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
        if self._reselecting:
            self._reselecting = False
            return
        sel = self.tree.selection()
        path = self._paths.get(sel[0]) if sel else None
        if not path or path == self._cur:
            return
        if self._unsaved_changes():               # don't silently drop an in-progress edit
            from tkinter import messagebox
            name = os.path.basename(self._cur or "")
            if not messagebox.askyesno("Unsaved changes",
                                       f"Discard unsaved changes to {name}?", parent=self):
                for item, known in self._paths.items():
                    if known == self._cur:
                        self._reselecting = True
                        self.tree.selection_set(item)
                        break
                return
        self._load(path)

    def _unsaved_changes(self) -> bool:
        """True while the shown viewer carries unsaved edits (the text pane or the CSV grid)."""
        if self._csv_dirty:
            return True
        return (self._text_editable and self._textw is not None
                and self._textw.winfo_exists() and bool(self._textw.edit_modified()))

    # --- dispatch + viewers --------------------------------------------------------------------- #
    def _load(self, path: str) -> None:
        self._cur = path
        kind = files_view.viewer_kind(path)
        try:
            if kind == "csv":
                self._show_csv(path)
            elif kind == "xlsx":
                self._show_xlsx(path)
            elif kind == "text" and highlight.kind_of(path):
                self._show_doc(path)          # yaml/json: Text (highlighted) ⇄ Object explorer
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
        self._text_editable = False
        self._csv_dirty = False
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

    def _show_csv(self, path: str) -> None:
        """The CSV grid, EDITABLE per cell: double-click a data cell, Enter commits, Save writes the
        table back in its own dialect (sniffed delimiter, CRLF, minimal quoting). Multi-line cells
        refuse the single-line editor (a bell); the header row stays display-only."""
        self._clear_editor()
        self._header(path)
        rows, delim = files_view.read_csv_rows_delim(path)
        bar = ttk.Frame(self.editor)
        bar.pack(side="top", fill="x", padx=6, pady=(0, 2))
        frame = ttk.Frame(self.editor)
        frame.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        if not rows:
            ttk.Label(frame, text="(empty)", padding=8).pack(anchor="nw")
            return
        header_row, data = rows[0], rows[1:]

        save_btn = ttk.Button(bar, text="Save")
        save_btn.pack(side="left")
        ttk.Button(bar, text="Revert", command=lambda: self._load(path)).pack(side="left", padx=6)
        dirty_lbl = ttk.Label(bar, text="")
        dirty_lbl.pack(side="left", padx=8)
        ttk.Label(bar, text="double-click a cell to edit").pack(side="right")

        def set_dirty(flag: bool):
            self._csv_dirty = flag
            dirty_lbl.configure(text="● modified" if flag else "")
            save_btn.configure(state="normal" if flag else "disabled")

        def on_edit(r: int, c: int, new: str) -> bool:
            row = data[r]
            while len(row) <= c:
                row.append("")
            if row[c] == new:
                return False                      # a no-op commit doesn't dirty the file
            row[c] = new
            set_dirty(True)
            return True

        def save():
            try:
                files_view.write_csv_rows(path, [header_row] + data, delim)
            except OSError as error:
                self.on_status(f"save failed: {error}")
                return
            set_dirty(False)
            self.on_status(f"saved {os.path.basename(path)}")

        save_btn.configure(command=save)
        set_dirty(False)
        grid = datagrid.DataGrid(frame, mode=self._mode, editable=True, on_edit=on_edit,
                                 raw_of=lambda r, c: data[r][c] if c < len(data[r]) else "")
        grid.pack(fill="both", expand=True)
        grid.set_data(header_row, data)

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
            if not rows:
                ttk.Label(holder, text="(empty sheet)", padding=8).pack(anchor="nw")
                return
            grid = datagrid.DataGrid(holder, mode=self._mode)
            grid.pack(side="top", fill="both", expand=True)
            grid.set_data(rows[0], rows[1:])

        box.bind("<<ComboboxSelected>>", lambda _e: show(box.get()))
        if names:
            box.set(names[0])
            show(names[0])

    def _show_text(self, path: str) -> None:
        self._clear_editor()
        self._header(path)
        self._text_body(path)

    def _show_doc(self, path: str) -> None:
        """A yaml/json document: the Text ⇄ Object-explorer toggle above the chosen view
        (UI_REFRESH_PLAN D). Text = read-only + syntax highlighting; Object = the scalar editor
        with `…` path pickers and an explicit Save."""
        self._clear_editor()
        self._header(path)
        row = ttk.Frame(self.editor)
        row.pack(side="top", fill="x", padx=6, pady=(0, 2))
        choice = tk.StringVar(value="object" if self._obj_mode else "text")

        def flip():
            self._obj_mode = choice.get() == "object"
            self._load(path)

        ttk.Radiobutton(row, text="Text", value="text", variable=choice, command=flip).pack(side="left")
        ttk.Radiobutton(row, text="Object explorer", value="object", variable=choice,
                        command=flip).pack(side="left", padx=10)
        if self._obj_mode:
            editor = object_editor.ObjectEditor(self.editor, path, on_status=self.on_status)
            editor.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        else:
            self._text_body(path)

    def _text_body(self, path: str) -> None:
        """The monospace text EDITOR (+ live yaml/json highlighting): text-based files edit in place
        and save ATOMICALLY with their original BOM/newline style (Save button / Ctrl+S; Revert
        re-reads). A file over the editor cap opens READ-ONLY - saving a truncated read would destroy
        the tail (Open externally instead)."""
        info = files_view.read_text_file(path)
        editable = not info["truncated"]
        bar = ttk.Frame(self.editor)
        bar.pack(side="top", fill="x", padx=6, pady=(0, 2))
        frame = ttk.Frame(self.editor)
        frame.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
        text = tk.Text(frame, wrap="none", relief="flat", borderwidth=0, undo=True,
                       background=theme.bg_for(self._mode), foreground=theme.fg_for(self._mode),
                       insertbackground=theme.fg_for(self._mode), font=theme.MONO_FONT)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        text.insert("1.0", info["text"])
        # highlighting above the cap would freeze every keystroke on a huge yaml/json - skip it there
        kind = highlight.kind_of(path) if len(info["text"]) <= files_view.HIGHLIGHT_CAP else None
        if kind:
            highlight.configure_tags(text, self._mode)
            highlight.apply(text, kind, info["text"])
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)
        self._textw = text
        self._text_editable = editable
        if not editable:
            text.configure(state="disabled")
            ttk.Label(bar, text=f"read-only: over the {files_view.TEXT_EDIT_CAP // 1_000_000} MB "
                                "editor cap - Open externally").pack(side="left")
            return

        save_btn = ttk.Button(bar, text="Save  (Ctrl+S)")
        save_btn.pack(side="left")
        ttk.Button(bar, text="Revert", command=lambda: self._load(path)).pack(side="left", padx=6)
        dirty_lbl = ttk.Label(bar, text="")
        dirty_lbl.pack(side="left", padx=8)
        hl_job = [None]

        def set_dirty(flag: bool):
            dirty_lbl.configure(text="● modified" if flag else "")
            save_btn.configure(state="normal" if flag else "disabled")

        def rehighlight():
            hl_job[0] = None
            if not text.winfo_exists():
                return
            content = text.get("1.0", "end-1c")
            for tag in highlight.COLORS:
                text.tag_remove(tag, "1.0", "end")
            highlight.apply(text, kind, content)

        def on_modified(_event=None):
            if text.edit_modified():
                set_dirty(True)
                if kind:                          # debounce the re-highlight while typing
                    if hl_job[0]:
                        text.after_cancel(hl_job[0])
                    hl_job[0] = text.after(200, rehighlight)

        def save(_event=None):
            try:
                files_view.write_text_file(path, text.get("1.0", "end-1c"),
                                           info["bom"], info["crlf"])
            except OSError as error:
                self.on_status(f"save failed: {error}")
                return "break"
            text.edit_modified(False)
            set_dirty(False)
            self.on_status(f"saved {os.path.basename(path)}")
            return "break"

        save_btn.configure(command=save)
        set_dirty(False)
        text.edit_modified(False)                 # the initial insert is not an edit
        text.bind("<<Modified>>", on_modified)
        text.bind("<Control-s>", save)

    def set_theme(self, mode: str) -> None:
        """Re-theme the panel for a light/dark switch. The ttk widgets follow the token styles; only the
        classic-tk text viewer needs its bg/fg set - reconfigure it live if one is shown."""
        self._mode = mode
        if self._textw is not None and self._textw.winfo_exists():
            self._textw.configure(background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                                  insertbackground=theme.fg_for(mode))
            if self._cur and highlight.kind_of(self._cur):
                highlight.configure_tags(self._textw, mode)
        # the canvas DataGrids don't follow ttk styles - re-render the shown grid file in the new
        # mode (an open xlsx falls back to its first sheet; the text/object views re-theme in place)
        if self._cur and files_view.viewer_kind(self._cur) in ("csv", "xlsx"):
            self._load(self._cur)
