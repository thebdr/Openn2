"""objedit.py - a structured object editor for YAML / JSON / XML (a ttk.Treeview of the parsed tree).

Edits each format IN ITS OWN structure and serializes back faithfully:
  - YAML -> ruamel `CommentedMap`/`CommentedSeq`, mutated in place so **comments survive** the edit;
  - JSON -> stdlib dict/list (type-preserving scalar edits);
  - XML  -> ElementTree (element text + attributes).
Leaf scalars are edited in place (double-click the Value cell). A **right-click context menu** adds the
structural edits: Browse a file/folder into a leaf, Add a key/item/element/attribute, Delete a node -
all mutating the in-memory tree (Save persists; comments + JSON scalar types are preserved). A
**Tree | Text** toggle drops to a raw monospace editor for edge cases (and re-parses on the way back).

No external dependency beyond ruamel (already required) - the off-the-shelf editors are JSON-only /
web-based and would strip YAML comments (see the library survey).
"""
from __future__ import annotations
import io
import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
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


# --- pure structural mutations (Tk-free, unit-tested) ------------------------------------------- #
_PATH_DIR_HINTS = ("dir", "folder", "output")


def _key_wants_dir(key: str) -> bool:
    """A leaf whose key hints at a directory (so the context menu offers 'Browse folder' first)."""
    return any(h in str(key).lower() for h in _PATH_DIR_HINTS)


def add_key(mapping, name: str) -> None:
    """Add a new empty-string scalar under a dict / ruamel CommentedMap; KeyError on a duplicate."""
    if name in mapping:
        raise KeyError(f"key {name!r} already exists")
    mapping[name] = ""


def add_item(seq) -> None:
    """Append a new empty-string scalar to a list / ruamel CommentedSeq."""
    seq.append("")


def delete_node(container, key, kind: str, node=None) -> None:
    """Remove a node from its container: a dict key / a list index / an XML element|attr|text."""
    if kind == "xml_elem":
        container.remove(node)
    elif kind == "xml_attr":
        container.attrib.pop(key, None)
    elif kind == "xml_text":
        container.text = ""
    else:                                   # dict key or list index
        del container[key]


class ObjectEditor(ttk.Frame):
    def __init__(self, parent, path, pal, font_family, on_status=lambda *_a: None, **kw):
        super().__init__(parent, **kw)
        self.path = path
        self.ext = os.path.splitext(path)[1].lower()
        self.pal = pal
        self.font_family = font_family
        self.on_status = on_status
        self._setters: dict = {}        # tree item id -> setter(new_str) for leaves
        self._model: dict = {}          # tree item id -> (kind, container, key, node) for the context menu
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
        self._model.clear()
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
            self._pop_xml("", self._data, None)
        else:
            self._pop("", os.path.basename(self.path), self._data, None, None)
        self.tree.bind("<Double-1>", self._begin_edit)
        self.tree.bind("<Button-3>", self._popup_menu)

    def _pop(self, parent, label, node, container, key):
        """Insert `node` (dict/list/scalar) under `parent`; record (kind, container, key, node) in
        `_model` for the context menu, and a leaf setter (container,key locate a scalar) for editing."""
        if isinstance(node, dict):
            item = self.tree.insert(parent, "end", text=label, values=("",), open=True)
            self._model[item] = ("dict", container, key, node)
            for k, v in node.items():
                self._pop(item, str(k), v, node, k)
        elif isinstance(node, (list, tuple)):
            item = self.tree.insert(parent, "end", text=label, values=(f"[{len(node)}]",), open=True)
            self._model[item] = ("list", container, key, node)
            for i, v in enumerate(node):
                self._pop(item, f"[{i}]", v, node, i)
        else:
            item = self.tree.insert(parent, "end", text=label,
                                    values=("" if node is None else str(node),))
            self._model[item] = ("scalar", container, key, node)
            if container is not None:
                self._setters[item] = lambda new, c=container, k=key, old=node: c.__setitem__(k, _coerce(new, old))

    def _pop_xml(self, parent, el, parent_el):
        item = self.tree.insert(parent, "end", text=el.tag, values=("",), open=True)
        self._model[item] = ("xml_elem", parent_el, None, el)        # container=parent element (None=root)
        for name, val in el.attrib.items():
            a = self.tree.insert(item, "end", text=f"@{name}", values=(val,))
            self._model[a] = ("xml_attr", el, name, val)
            self._setters[a] = lambda new, e=el, n=name: e.set(n, new)
        if el.text and el.text.strip():
            t = self.tree.insert(item, "end", text="#text", values=(el.text.strip(),))
            self._model[t] = ("xml_text", el, None, el.text)
            self._setters[t] = lambda new, e=el: setattr(e, "text", new)
        for child in list(el):
            self._pop_xml(item, child, el)

    # ---- in-place leaf editing ------------------------------------------ #
    def _begin_edit(self, event):
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if item and item in self._setters:
            self._edit_item(item)

    def _edit_item(self, item):
        """Open the in-place Value editor for a leaf (double-click, or right after Add key/item)."""
        if item not in self._setters:
            return
        self.tree.see(item)
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

    # ---- context menu: browse / add / delete ---------------------------- #
    def _popup_menu(self, event):
        self._cancel_edit()
        item = self.tree.identify_row(event.y)
        if not item or item not in self._model:
            return
        self.tree.selection_set(item)
        kind, container, _key, _node = self._model[item]
        menu = tk.Menu(self.tree, tearoff=False)
        if kind == "scalar":
            opts = [("Browse file…", "file"), ("Browse folder…", "dir")]
            if _key_wants_dir(self.tree.item(item, "text")):
                opts.reverse()                          # a dir-ish key offers the folder picker first
            for label, which in opts:
                menu.add_command(label=label, command=lambda it=item, w=which: self._browse(it, w))
        elif kind == "dict":
            menu.add_command(label="Add key…", command=lambda it=item: self._add_child(it, "dict"))
        elif kind == "list":
            menu.add_command(label="Add item…", command=lambda it=item: self._add_child(it, "list"))
        elif kind == "xml_elem":
            menu.add_command(label="Add child element…", command=lambda it=item: self._add_child(it, "xml_child"))
            menu.add_command(label="Add attribute…", command=lambda it=item: self._add_child(it, "xml_attr"))
        if container is not None:                       # the root has no container -> not deletable
            menu.add_separator()
            menu.add_command(label="Delete", command=lambda it=item: self._delete(it))
        if menu.index("end") is not None:
            menu.tk_popup(event.x_root, event.y_root)

    def _browse(self, item, which):
        """Pick a file/folder into a leaf - reuses the leaf's setter so the backing data updates."""
        cur = self.tree.set(item, "value")
        initial = os.path.dirname(cur) if cur and os.path.isabs(cur) else os.getcwd()
        if which == "dir":
            picked = filedialog.askdirectory(parent=self, title="Select folder", initialdir=initial)
        else:
            picked = filedialog.askopenfilename(parent=self, title="Select file", initialdir=initial)
        if not picked:
            return
        picked = os.path.normpath(picked)
        self.tree.set(item, "value", picked)
        setter = self._setters.get(item)
        if setter is not None:
            try:
                setter(picked)
            except Exception as e:  # noqa: BLE001
                self.on_status(f"set failed: {e}")
                return
        self.on_status(f"{self.tree.item(item, 'text')} = {picked}")

    def _add_child(self, item, kind):
        node = self._model[item][3]
        if kind == "dict":
            name = simpledialog.askstring("Add key", "New key name:", parent=self)
            if not name:
                return
            try:
                add_key(node, name)
            except KeyError as e:
                self.on_status(str(e))
                return
            self._add_leaf(item, name, node, name)
            self.on_status(f"added {name}")
        elif kind == "list":
            add_item(node)
            idx = len(node) - 1
            self.tree.set(item, "value", f"[{len(node)}]")
            self._add_leaf(item, f"[{idx}]", node, idx)
            self.on_status("added item")
        elif kind == "xml_child":
            tag = simpledialog.askstring("Add child element", "Element tag:", parent=self)
            if not tag:
                return
            ET.SubElement(node, tag)
            self._show_tree()
            self.on_status(f"added <{tag}>")
        elif kind == "xml_attr":
            name = simpledialog.askstring("Add attribute", "Attribute name:", parent=self)
            if not name:
                return
            node.set(name, "")
            self._show_tree()
            self.on_status(f"added @{name}")

    def _add_leaf(self, parent_item, label, container, key):
        """Insert one new empty scalar leaf incrementally (append needs no sibling reindex), register it,
        then open it for editing - mirrors `_pop`'s scalar branch."""
        child = self.tree.insert(parent_item, "end", text=label, values=("",))
        self._model[child] = ("scalar", container, key, "")
        self._setters[child] = lambda new, c=container, k=key, old="": c.__setitem__(k, _coerce(new, old))
        self.tree.item(parent_item, open=True)
        self.tree.selection_set(child)
        self._edit_item(child)

    def _delete(self, item):
        kind, container, key, node = self._model[item]
        if container is None:
            return
        try:
            delete_node(container, key, kind, node)
        except Exception as e:  # noqa: BLE001
            self.on_status(f"delete failed: {e}")
            return
        self._show_tree()                               # full re-pop: list indices reindex correctly
        self.on_status("deleted")

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
