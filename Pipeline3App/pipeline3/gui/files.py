"""files.py - the Files tab: a 3-section file tree beside a type-aware editor.

Tree sections (caller-supplied): Project configuration / User editable files / Bare output files.
The editor picks a view by extension:
  - .csv                         -> an editable tksheet grid (Save writes comma CSV - the contract);
  - .yaml/.json/.scl/.db/.xml/.txt -> an editable monospace text editor (Save writes the text);
  - .xlsx/.xlsm                  -> a READ-ONLY value grid (openpyxl data_only) + "Edit externally"
                                    (LibreOffice/Excel - never risks the formulas/array-formula/VBA the
                                    pipeline relies on; see extedit.py).
"""
from __future__ import annotations
import csv as _csv
import os
import tkinter as tk
from tkinter import ttk

from tksheet import Sheet

from pipeline3.io import csv_tables
from pipeline3.gui import extedit, objedit, grid, widgets

_OBJ_EXT = (".yaml", ".yml", ".json", ".xml")        # -> the structured object editor (tree)
_TEXT_EXT = (".scl", ".db", ".txt", ".md", ".log")   # -> the plain text editor
_GRID_EXT = (".csv",)
_XLSX_EXT = (".xlsx", ".xlsm", ".xls")
_SHOW_EXT = _OBJ_EXT + _TEXT_EXT + _GRID_EXT + _XLSX_EXT
_SKIP = ("__pycache__", ".pyc")
_MAX_ROWS, _MAX_COLS = 1000, 80          # xlsx preview cap


def _allowed(name: str) -> bool:
    low = name.lower()
    if low.startswith("~$") or low.endswith(".pyc") or ".bak_" in low or "__pycache__" in low:
        return False
    return low.endswith(_SHOW_EXT)


class FilesPanel(ttk.Frame):
    def __init__(self, parent, pal, font_family, sections, on_status=lambda *_a: None, dark=True, **kw):
        super().__init__(parent, **kw)
        self.pal = pal
        self.font_family = font_family
        self.sections = sections                 # [(label, [paths])]
        self.on_status = on_status
        self.dark = dark
        self._paths: dict = {}                    # tree item id -> absolute file path
        self._cur = None                          # the loaded file path

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tvs = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tvs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tvs.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._tree_menu)
        ttk.Button(left, text="Refresh", command=self.refresh).pack(side="bottom", fill="x")
        paned.add(left, weight=1)

        self.editor = ttk.Frame(paned)
        paned.add(self.editor, weight=4)
        self._placeholder("Select a file from the tree.")
        self.refresh()

    # ---- tree ------------------------------------------------------------ #
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        for label, roots in self.sections:
            node = self.tree.insert("", "end", text=label, open=True)
            count = 0
            for root in roots:
                count += self._populate(node, root)
            if count == 0:
                self.tree.insert(node, "end", text="(empty)")

    def _populate(self, parent, path) -> int:
        if not path or not os.path.exists(path):
            return 0
        if os.path.isfile(path):
            if _allowed(os.path.basename(path)):
                item = self.tree.insert(parent, "end", text=os.path.basename(path))
                self._paths[item] = os.path.abspath(path)
                return 1
            return 0
        count = 0
        try:
            entries = sorted(os.scandir(path), key=lambda e: (e.is_file(), e.name.lower()))
        except OSError:
            return 0
        for e in entries:
            if e.name in _SKIP or e.name.startswith("."):
                continue
            if e.is_dir():
                sub = self.tree.insert(parent, "end", text=e.name + "/", open=False)
                n = self._populate(sub, e.path)
                if n == 0:
                    self.tree.delete(sub)
                count += n
            elif _allowed(e.name):
                item = self.tree.insert(parent, "end", text=e.name)
                self._paths[item] = os.path.abspath(e.path)
                count += 1
        return count

    def _on_select(self, _e):
        sel = self.tree.selection()
        path = self._paths.get(sel[0]) if sel else None
        if path:
            self._load(path)

    def _tree_menu(self, event):
        item = self.tree.identify_row(event.y)
        path = self._paths.get(item)
        if not path:
            return
        self.tree.selection_set(item)
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(label="Open containing folder",
                         command=lambda p=path: self.on_status(extedit.reveal(p)[1]))
        menu.add_command(label="Open externally",
                         command=lambda p=path: self.on_status(extedit.open_external(p)[1]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ---- editor dispatch ------------------------------------------------- #
    def _clear_editor(self):
        for w in self.editor.winfo_children():
            w.destroy()

    def _placeholder(self, msg):
        self._clear_editor()
        ttk.Label(self.editor, text=msg, padding=20).pack(anchor="nw")

    def _toolbar(self, path, *, save=None, external=False):
        header, bar = widgets.editor_header(self.editor, path, self.on_status)
        header.pack(side="top", fill="x")
        ttk.Button(bar, text="Reload", command=lambda: self._load(path)).pack(side="right")
        if external:
            ttk.Button(bar, text="Edit externally",
                       command=lambda: self._external(path)).pack(side="right", padx=6)
        if save is not None:
            ttk.Button(bar, text="Save", command=save).pack(side="right", padx=6)
        return bar

    def _load(self, path):
        self._cur = path
        low = path.lower()
        try:
            if low.endswith(_GRID_EXT):
                self._csv(path)
            elif low.endswith(_XLSX_EXT):
                self._xlsx(path)
            elif low.endswith(_OBJ_EXT):
                self._obj(path)
            elif low.endswith(_TEXT_EXT):
                self._text(path)
            else:
                self._placeholder(f"{os.path.basename(path)}: preview not supported - Edit externally.")
        except Exception as e:  # noqa: BLE001
            self._placeholder(f"could not open {os.path.basename(path)}: {e}")

    def _sheet_theme(self):
        return "dark blue" if self.dark else "light blue"

    # ---- CSV (editable grid) --------------------------------------------- #
    def _csv(self, path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
        delim = csv_tables._sniff_delim(text)
        rows = list(_csv.reader(text.splitlines(), delimiter=delim))
        self._clear_editor()
        sheet = Sheet(self.editor, theme=self._sheet_theme(), data=rows or [[""]])
        sheet.enable_bindings()                                  # full editing
        self._toolbar(path, save=lambda s=sheet, p=path: self._save_csv(s, p))
        sheet.pack(side="top", fill="both", expand=True)
        self._grid = grid.decorate(sheet, self.dark)            # zebra + right-click sort/filter

    def _save_csv(self, sheet, path):
        rows = sheet.get_sheet_data()
        csv_tables.write_table(path, None, rows)                 # comma on write (the contract)
        self.on_status(f"saved {os.path.basename(path)} ({len(rows)} row(s), comma CSV)")

    # ---- xlsx/xlsm (read-only value grid) -------------------------------- #
    def _xlsx(self, path):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True, read_only=True)
        try:
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= _MAX_ROWS:
                    break
                rows.append(["" if c is None else str(c) for c in row[:_MAX_COLS]])
        finally:
            wb.close()
        self._clear_editor()
        sheet = Sheet(self.editor, theme=self._sheet_theme(), data=rows or [[""]])
        sheet.enable_bindings("single_select", "drag_select", "row_select", "column_select",
                              "column_width_resize", "arrowkeys", "copy", "rc_select")
        self._toolbar(path, external=True)                       # edit happens in LibreOffice/Excel
        note = (f"read-only preview of '{ws.title}' (values only; capped {_MAX_ROWS}x{_MAX_COLS}). "
                f"Edit externally to keep formulas/macros.")
        ttk.Label(self.editor, text=note, padding=(6, 2)).pack(side="bottom", anchor="w")
        sheet.pack(side="top", fill="both", expand=True)
        self._grid = grid.decorate(sheet, self.dark)            # zebra + right-click sort/filter

    # ---- text editor ----------------------------------------------------- #
    def _text(self, path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            content = f.read()
        self._clear_editor()
        txt = tk.Text(self.editor, wrap="none", undo=True, font=(self.font_family, 10),
                      background=self.pal["log_bg"], foreground=self.pal["log_fg"],
                      insertbackground=self.pal["fg"], relief="flat", padx=8, pady=6)
        vs = ttk.Scrollbar(self.editor, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vs.set)
        self._toolbar(path, save=lambda t=txt, p=path: self._save_text(t, p))
        vs.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", content)

    def _save_text(self, txt, path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(txt.get("1.0", "end-1c"))
        self.on_status(f"saved {os.path.basename(path)}")

    def _obj(self, path):
        self._clear_editor()
        ed = objedit.ObjectEditor(self.editor, path, self.pal, self.font_family, on_status=self.on_status)
        ed.pack(side="top", fill="both", expand=True)

    def _external(self, path):
        ok, msg = extedit.open_external(path)
        self.on_status(msg)

    # ---- theming --------------------------------------------------------- #
    def retheme(self, pal, dark):
        self.pal, self.dark = pal, dark
        if self._cur:
            self._load(self._cur)                                # rebuild the current view in new colours
