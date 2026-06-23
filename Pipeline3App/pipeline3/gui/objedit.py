"""objedit.py - a structured object editor for YAML / JSON / XML (a ttk.Treeview of the parsed tree).

Edits each format IN ITS OWN structure and serializes back faithfully:
  - YAML -> ruamel `CommentedMap`/`CommentedSeq`, mutated in place so **comments survive** the edit;
  - JSON -> stdlib dict/list (type-preserving scalar edits);
  - XML  -> ElementTree (element text + attributes).
Leaf scalars are edited in place (double-click the Value cell). A **Tree | Text** toggle drops to a raw
monospace editor for edge cases (and re-parses on the way back). Save writes the current view.

No external dependency beyond ruamel (already required) - the off-the-shelf editors are JSON-only /
web-based and would strip YAML comments (see the library survey).
"""
from __future__ import annotations
import io
import json
import os
import tkinter as tk
from tkinter import ttk
import xml.etree.ElementTree as ET

from pipeline3.gui import widgets


def _coerce(new: str, old):
    """Keep a JSON/YAML scalar's type across an edit where possible (bool/int/float), else string."""
    if isinstance(old, bool):
        return new.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(old, int) and not isinstance(old, bool):
        try:
            return int(new)
        except ValueError:
            return new
    if isinstance(old, float):
        try:
            return float(new)
        except ValueError:
            return new
    return new


class ObjectEditor(ttk.Frame):
    def __init__(self, parent, path, pal, font_family, on_status=lambda *_a: None, **kw):
        super().__init__(parent, **kw)
        self.path = path
        self.ext = os.path.splitext(path)[1].lower()
        self.pal = pal
        self.font_family = font_family
        self.on_status = on_status
        self._setters: dict = {}        # tree item id -> setter(new_str) for leaves
        self._cell = None               # the in-place edit Entry
        self._mode = "tree"
        self._textw = None
        with open(path, encoding="utf-8-sig") as f:
            self._raw = f.read()
        self._yaml = None
        self._data = self._parse(self._raw)

        header, bar = widgets.editor_header(self, path, on_status)
        header.pack(side="top", fill="x")
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="right")
        self._mode_btn = ttk.Button(bar, text="Text view", command=self._toggle_mode)
        self._mode_btn.pack(side="right", padx=6)
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=6)
        self.body = ttk.Frame(self)
        self.body.pack(side="top", fill="both", expand=True)
        self._show_tree()

    # ---- parse / dump per format ---------------------------------------- #
    def _parse(self, text):
        if self.ext in (".yaml", ".yml"):
            from ruamel.yaml import YAML
            self._yaml = YAML()
            self._yaml.preserve_quotes = True
            self._yaml.width = 4096           # don't re-wrap long lines on save (preserve formatting)
            return self._yaml.load(text) if text.strip() else {}
        if self.ext == ".json":
            return json.loads(text) if text.strip() else {}
        return ET.fromstring(text)                       # .xml

    def _dump(self, data) -> str:
        if self.ext in (".yaml", ".yml"):
            s = io.StringIO()
            self._yaml.dump(data, s)
            return s.getvalue()
        if self.ext == ".json":
            return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        return ET.tostring(data, encoding="unicode")

    # ---- the tree view -------------------------------------------------- #
    def _show_tree(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._setters.clear()
        self.tree = ttk.Treeview(self.body, columns=("value",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Key")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=320, stretch=False)
        self.tree.column("value", width=460)
        vs = ttk.Scrollbar(self.body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        if self.ext == ".xml":
            self._pop_xml("", self._data)
        else:
            self._pop("", os.path.basename(self.path), self._data, None, None)
        self.tree.bind("<Double-1>", self._begin_edit)

    def _pop(self, parent, label, node, container, key):
        """Insert `node` (dict/list/scalar) under `parent`. (container,key) locate a scalar for editing."""
        if isinstance(node, dict):
            item = self.tree.insert(parent, "end", text=label, values=("",), open=True)
            for k, v in node.items():
                self._pop(item, str(k), v, node, k)
        elif isinstance(node, (list, tuple)):
            item = self.tree.insert(parent, "end", text=label, values=(f"[{len(node)}]",), open=True)
            for i, v in enumerate(node):
                self._pop(item, f"[{i}]", v, node, i)
        else:
            item = self.tree.insert(parent, "end", text=label,
                                    values=("" if node is None else str(node),))
            if container is not None:
                self._setters[item] = lambda new, c=container, k=key, old=node: c.__setitem__(k, _coerce(new, old))

    def _pop_xml(self, parent, el):
        item = self.tree.insert(parent, "end", text=el.tag, values=("",), open=True)
        for name, val in el.attrib.items():
            a = self.tree.insert(item, "end", text=f"@{name}", values=(val,))
            self._setters[a] = lambda new, e=el, n=name: e.set(n, new)
        if el.text and el.text.strip():
            t = self.tree.insert(item, "end", text="#text", values=(el.text.strip(),))
            self._setters[t] = lambda new, e=el: setattr(e, "text", new)
        for child in list(el):
            self._pop_xml(item, child)

    # ---- in-place leaf editing ------------------------------------------ #
    def _begin_edit(self, event):
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item or item not in self._setters:
            return
        bbox = self.tree.bbox(item, "#1")
        if not bbox:
            return
        x, y, w, h = bbox
        self._cancel_edit()
        self._cell = tk.Entry(self.tree)
        self._cell.insert(0, self.tree.set(item, "value"))
        self._cell.select_range(0, "end")
        self._cell.place(x=x, y=y, width=w, height=h)
        self._cell.focus_set()
        self._cell.bind("<Return>", lambda e: self._commit(item))
        self._cell.bind("<Escape>", lambda e: self._cancel_edit())
        self._cell.bind("<FocusOut>", lambda e: self._commit(item))

    def _commit(self, item):
        if self._cell is None:
            return
        new = self._cell.get()
        self._cancel_edit()
        self.tree.set(item, "value", new)
        try:
            self._setters[item](new)
            self.on_status(f"{self.tree.item(item, 'text')} = {new}")
        except Exception as e:  # noqa: BLE001
            self.on_status(f"edit failed: {e}")

    def _cancel_edit(self):
        if self._cell is not None:
            self._cell.destroy()
            self._cell = None

    # ---- text view + toggle --------------------------------------------- #
    def _show_text(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._textw = tk.Text(self.body, wrap="none", undo=True, font=(self.font_family, 10),
                              background=self.pal["log_bg"], foreground=self.pal["log_fg"],
                              insertbackground=self.pal["fg"], relief="flat", padx=8, pady=6)
        vs = ttk.Scrollbar(self.body, orient="vertical", command=self._textw.yview)
        self._textw.configure(yscrollcommand=vs.set)
        self._textw.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self._textw.insert("1.0", self._raw)

    def _toggle_mode(self):
        if self._mode == "tree":
            self._raw = self._dump(self._data)           # capture tree edits
            self._mode = "text"
            self._mode_btn.configure(text="Tree view")
            self._show_text()
        else:
            raw = self._textw.get("1.0", "end-1c")
            try:
                self._data = self._parse(raw)
            except Exception as e:  # noqa: BLE001
                self.on_status(f"parse error - staying in text: {e}")
                return
            self._raw = raw
            self._mode = "tree"
            self._mode_btn.configure(text="Text view")
            self._show_tree()

    # ---- save / reload --------------------------------------------------- #
    def save(self):
        self._cancel_edit()
        text = self._dump(self._data) if self._mode == "tree" else self._textw.get("1.0", "end-1c")
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self._raw = text
        if self._mode == "text":                          # re-sync the model from saved text
            try:
                self._data = self._parse(text)
            except Exception:  # noqa: BLE001
                pass
        self.on_status(f"saved {os.path.basename(self.path)}")

    def reload(self):
        with open(self.path, encoding="utf-8-sig") as f:
            self._raw = f.read()
        self._data = self._parse(self._raw)
        if self._mode == "tree":
            self._show_tree()
        else:
            self._show_text()
        self.on_status(f"reloaded {os.path.basename(self.path)}")
