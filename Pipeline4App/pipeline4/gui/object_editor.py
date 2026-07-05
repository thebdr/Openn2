"""The YAML/JSON *Object explorer* view (UI_REFRESH_PLAN D): a key/value tree over the document with
INLINE SCALAR EDITING and a `…` filesystem picker on path-like keys, saving losslessly.

Model (Tk-free, tested):
  * `load_document(path)` -> `(doc, kind)` - YAML through ruamel round-trip (comments/order/quotes
    survive a save), JSON through the stdlib (dict order preserved).
  * `get_at`/`set_at(doc, path_tuple, text)` - `set_at` COERCES the new text to the OLD scalar's type
    (bool/int/float stay typed; anything unparsable stays a string) so an edited yaml keeps its types.
  * `dump_document(path, doc, kind)` - ATOMIC write (temp + os.replace); yaml round-trip, json indent=2.
  * `path_role(key)` - the `…` picker kind: a key containing dir/folder/root -> "dir"; containing
    path -> "file"; else None. Case-insensitive (the user's spec: any key containing "path").
  * `picked_value(old, chosen, base_dir)` - a picked path stays RELATIVE when the old value was
    relative and the choice is under `base_dir`; otherwise absolute.

View: `ObjectEditor(parent, path, on_status)` - a 2-column Treeview (keys tree + values), double-click
a value to edit in place (Enter commits, Escape cancels), `…` column click opens the picker, Save
writes via the model (dirty marker; scalar edits only - add/remove keys is a text/external edit).
"""
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, ttk

_PATH_DIR_WORDS = ("dir", "folder", "root")


# --- the Tk-free model --------------------------------------------------------------------------- #
def load_document(path: str) -> tuple:
    """Parse `path` -> `(document, kind)` with kind in {'yaml', 'json', 'xml'}. Raises on a broken
    file (the caller falls back to the text view with the error). XML parses to its root Element and
    the explorer shows it READ-ONLY: an ElementTree re-write would drop comments/formatting - and the
    BuilderData XMLs are byte-parity surfaces - so XML edits belong in the Text mode."""
    low = path.lower()
    if low.endswith((".yaml", ".yml")):
        from ruamel.yaml import YAML
        parser = YAML()                      # round-trip: comments + key order + quotes survive
        parser.preserve_quotes = True
        with open(path, encoding="utf-8") as handle:
            return parser.load(handle), "yaml"
    if low.endswith(".json"):
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle), "json"
    if low.endswith(".xml"):
        import xml.etree.ElementTree as ET
        return ET.parse(path).getroot(), "xml"
    raise ValueError(f"not a yaml/json/xml document: {os.path.basename(path)}")


def _is_element(value) -> bool:
    """True for an ElementTree Element (duck-typed - Element is a C type, isinstance is brittle)."""
    return hasattr(value, "tag") and hasattr(value, "attrib") and hasattr(value, "iter")


def xml_items(elem) -> list:
    """The explorer rows of one XML element, in document order: ('@name', value) per attribute, a
    ('#text', text) row when the element carries non-blank text, then the child elements - duplicate
    tags get an ' [n]' suffix so every row reads uniquely."""
    items = [(f"@{k}", v) for k, v in elem.attrib.items()]
    text = (elem.text or "").strip()
    if text:
        items.append(("#text", text))
    totals: dict = {}
    for child in elem:
        totals[child.tag] = totals.get(child.tag, 0) + 1
    seen: dict = {}
    for child in elem:
        seen[child.tag] = seen.get(child.tag, 0) + 1
        label = child.tag if totals[child.tag] == 1 else f"{child.tag} [{seen[child.tag]}]"
        items.append((label, child))
    return items


def dump_document(path: str, doc, kind: str) -> None:
    """Write `doc` back ATOMICALLY (temp file + os.replace - a crash never truncates the original)."""
    tmp = f"{path}.tmp_objedit"
    if kind == "yaml":
        from ruamel.yaml import YAML
        writer = YAML()
        writer.preserve_quotes = True
        writer.width = 4096                  # never re-wrap long lines the user authored
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            writer.dump(doc, handle)
    else:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(doc, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    os.replace(tmp, path)


def get_at(doc, path_tuple):
    node = doc
    for key in path_tuple:
        node = node[key]
    return node


def coerce(old, text: str):
    """The new scalar for an edit: typed like the OLD value when the text parses as that type
    (bool BEFORE int - bool subclasses int), else the raw string."""
    stripped = str(text).strip()
    if isinstance(old, bool):
        low = stripped.lower()
        if low in ("true", "yes", "on", "1"):
            return True
        if low in ("false", "no", "off", "0"):
            return False
        return text
    if isinstance(old, int):
        try:
            return int(stripped)
        except ValueError:
            return text
    if isinstance(old, float):
        try:
            return float(stripped)
        except ValueError:
            return text
    return text


def set_at(doc, path_tuple, text: str) -> None:
    """Replace the scalar at `path_tuple` with `text` coerced to the old value's type."""
    parent = get_at(doc, path_tuple[:-1]) if len(path_tuple) > 1 else doc
    key = path_tuple[-1]
    parent[key] = coerce(parent[key], text)


def path_role(key) -> str | None:
    """The `…` picker a key gets: 'dir' when the key names a directory (dir/folder/root), 'file' when
    it contains 'path' (the user's spec, case-insensitive), else None."""
    low = str(key).lower()
    if any(word in low for word in _PATH_DIR_WORDS):
        return "dir"
    if "path" in low:
        return "file"
    return None


def picked_value(old, chosen: str, base_dir: str) -> str:
    """The value a picker choice lands as: RELATIVE (/-separated) when the old value was relative and
    the choice sits under `base_dir`; absolute otherwise."""
    old_text = str(old or "")
    if old_text and not os.path.isabs(old_text):
        rel = os.path.relpath(chosen, base_dir)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
    return chosen


def is_scalar(value) -> bool:
    return not isinstance(value, (dict, list))


def add_list_neighbor(doc, path_tuple) -> tuple:
    """The right-click 'Add element' on a LIST member: insert a DEEP COPY of it right after itself
    (the structure duplicates - the user then edits the values, which beats typing a section from
    scratch). Returns the new member's path."""
    import copy
    parent = get_at(doc, path_tuple[:-1]) if len(path_tuple) > 1 else doc
    index = path_tuple[-1]
    if not isinstance(index, int) or not isinstance(parent, list):
        raise ValueError("not a list member")
    parent.insert(index + 1, copy.deepcopy(parent[index]))
    return path_tuple[:-1] + (index + 1,)


def add_dict_neighbor(doc, path_tuple, new_key: str) -> tuple:
    """'Add element' on a MAPPING entry: insert `new_key` (an empty-string value) right AFTER it,
    order preserved (a ruamel CommentedMap inserts in place so comments survive; a plain json dict
    rebuilds its order). Raises when the key already exists."""
    parent = get_at(doc, path_tuple[:-1]) if len(path_tuple) > 1 else doc
    key = path_tuple[-1]
    if not isinstance(parent, dict):
        raise ValueError("not a mapping entry")
    if new_key in parent:
        raise ValueError(f"key {new_key!r} already exists")
    position = list(parent).index(key) + 1
    if hasattr(parent, "insert"):                 # ruamel CommentedMap - comment-preserving insert
        parent.insert(position, new_key, "")
    else:
        items = list(parent.items())
        items.insert(position, (new_key, ""))
        parent.clear()
        parent.update(items)
    return path_tuple[:-1] + (new_key,)


# --- the Tk view ---------------------------------------------------------------------------------- #
class ObjectEditor(ttk.Frame):
    """The key/value tree + inline editing + `…` pickers + Save/Revert over one yaml/json document
    (xml = a read-only structure view). Zebra rows + column dividers + the text-mode highlight
    palette on the values; right-click 'Add element' inserts a NEIGHBOR (a duplicated list member /
    a new mapping key after the clicked one); Expand/Collapse all."""

    def __init__(self, parent, path: str, on_status=lambda *_a: None, mode: str = "dark"):
        super().__init__(parent)
        self._path = path
        self._on_status = on_status
        self._mode = "dark" if mode == "dark" else "light"
        self._doc = None
        self._kind = ""
        self._dirty = False
        self._rows: dict = {}                # tree item id -> (path_tuple, role, editable)
        self._row_n = 0                      # the zebra counter (reset per rebuild)
        self._editbox: tk.Entry | None = None

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", pady=(0, 3))
        self._save_btn = ttk.Button(bar, text="Save", command=self.save, state="disabled")
        self._save_btn.pack(side="left")
        ttk.Button(bar, text="Revert", command=self.reload).pack(side="left", padx=6)
        ttk.Button(bar, text="Expand all", command=lambda: self._set_open_all(True)
                   ).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Collapse all", command=lambda: self._set_open_all(False)
                   ).pack(side="left", padx=(4, 0))
        self._dirty_lbl = ttk.Label(bar, text="")
        self._dirty_lbl.pack(side="left", padx=8)
        self._hint = ttk.Label(bar, text="double-click a value to edit · … picks a path")
        self._hint.pack(side="right")

        holder = ttk.Frame(self)
        holder.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(holder, columns=("value", "pick"), show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="key")
        self.tree.heading("value", text="value")
        self.tree.heading("pick", text="")
        self.tree.column("#0", width=260, anchor="w")
        self.tree.column("value", width=420, anchor="w")
        self.tree.column("pick", width=34, anchor="center", stretch=False)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self._configure_row_tags()
        # the COLUMN DIVIDERS: Treeview draws no cell gridlines - two 1px overlays track the
        # key|value and value|pick boundaries (repositioned on resize + heading drags)
        from pipeline4.gui import theme
        line = theme.TOKENS[self._mode]["grid_line"]
        self._dividers = [tk.Frame(self.tree, width=1, bg=line) for _ in range(2)]
        for event in ("<Configure>", "<B1-Motion>", "<ButtonRelease-1>"):
            self.tree.bind(event, lambda _e: self._place_dividers(), "+")
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Button-1>", self._on_click, "+")
        self.tree.bind("<Button-3>", self._context_menu)
        self.reload()
        self.after_idle(self._place_dividers)

    # --- chrome ------------------------------------------------------------------------------------ #
    def _configure_row_tags(self) -> None:
        """Zebra backgrounds + the text-mode highlight palette on the row foregrounds (a Treeview tag
        styles the whole ROW; the value's type picks the colour - containers read as keys)."""
        from pipeline4.gui import highlight, theme
        dark = self._mode == "dark"
        tokens = theme.TOKENS[self._mode]
        self.tree.tag_configure("z1", background=tokens["field_alt"])
        self.tree.tag_configure("z0", background=tokens["field"])
        for tag, hl in (("t_key", "hl_key"), ("t_str", "hl_str"),
                        ("t_num", "hl_num"), ("t_bool", "hl_bool")):
            self.tree.tag_configure(tag, foreground=highlight.COLORS[hl][0 if dark else 1])

    def _type_tag(self, value) -> str:
        if isinstance(value, bool) or value is None:
            return "t_bool"
        if isinstance(value, (int, float)):
            return "t_num"
        return "t_str"

    def _tags_for(self, type_tag: str) -> tuple:
        self._row_n += 1
        return (type_tag, "z1" if self._row_n % 2 else "z0")

    def _place_dividers(self) -> None:
        """Track the column boundaries: key|value at #0's width, value|pick at (width - pick)."""
        try:
            x1 = int(self.tree.column("#0", "width"))
            x2 = self.tree.winfo_width() - int(self.tree.column("pick", "width"))
        except tk.TclError:
            return
        heights = self.tree.winfo_height()
        for divider, x in zip(self._dividers, (x1, x2)):
            if 0 < x < self.tree.winfo_width():
                divider.place(x=x, y=0, height=heights)
            else:
                divider.place_forget()

    def _set_open_all(self, open_: bool) -> None:
        def walk(item):
            self.tree.item(item, open=open_)
            for child in self.tree.get_children(item):
                walk(child)
        for top in self.tree.get_children(""):
            walk(top)

    # --- model <-> tree --------------------------------------------------------------------------- #
    def reload(self) -> None:
        self._close_edit()
        try:
            self._doc, self._kind = load_document(self._path)
        except Exception as error:  # noqa: BLE001
            self._doc, self._kind = None, ""
            self._set_dirty(False)
            self.tree.delete(*self.tree.get_children())
            self.tree.insert("", "end", text=f"could not parse: {error}")
            return
        self._set_dirty(False)
        if self._kind == "xml":              # a read-only structure view (see load_document)
            self._hint.configure(text="XML structure is read-only - edit in Text mode")
        else:
            self._hint.configure(text="double-click a value to edit · … picks a path")
        self._rebuild()

    def _rebuild(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        self._row_n = 0
        if self._kind == "xml":              # show the root element as the top node
            self._fill("", {f"<{self._doc.tag}>": self._doc}, ())
        else:
            self._fill("", self._doc, ())

    def _fill(self, parent, node, path_tuple) -> None:
        editable = self._kind != "xml"       # xml is the read-only structure view
        if _is_element(node):
            items = xml_items(node)
        elif isinstance(node, dict):
            items = node.items()
        elif isinstance(node, list):
            items = ((f"[{i}]", v) for i, v in enumerate(node))
        else:
            return
        for key, value in items:
            child_path = path_tuple + ((key if not str(key).startswith("[") else int(str(key)[1:-1])),)
            if _is_element(value):
                item = self.tree.insert(parent, "end", text=str(key), open=True,
                                        values=(f"<{value.tag}>", ""), tags=self._tags_for("t_key"))
                self._fill(item, value, child_path)
            elif is_scalar(value):
                role = path_role(key) if editable else None
                item = self.tree.insert(parent, "end", text=str(key), open=True,
                                        values=(self._render(value), "…" if role else ""),
                                        tags=self._tags_for(self._type_tag(value)))
                if editable:
                    self._rows[item] = (child_path, role, True)
            else:
                mark = "{…}" if isinstance(value, dict) else f"[{len(value)}]"
                item = self.tree.insert(parent, "end", text=str(key), open=True, values=(mark, ""),
                                        tags=self._tags_for("t_key"))
                if editable:                 # containers register for the Add-element menu only
                    self._rows[item] = (child_path, None, False)
                self._fill(item, value, child_path)

    @staticmethod
    def _render(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._dirty_lbl.configure(text="● modified" if dirty else "")
        self._save_btn.configure(state="normal" if dirty else "disabled")

    # --- editing ----------------------------------------------------------------------------------- #
    def _on_double(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if self.tree.identify_column(event.x) != "#1" or item not in self._rows:
            return
        if self._rows[item][2]:              # editable scalars only (containers register for the menu)
            self._open_edit(item)

    def _on_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if self.tree.identify_column(event.x) != "#2" or item not in self._rows:
            return
        path_tuple, role, _editable = self._rows[item]
        if role:
            self._pick(item, path_tuple, role)

    def _context_menu(self, event) -> None:
        """Right-click a row -> 'Add element': a NEIGHBOR inserted right after the clicked one - a
        list member duplicates its structure, a mapping entry prompts for the new key. Only for the
        relevant types (list members / mapping entries; xml is read-only)."""
        item = self.tree.identify_row(event.y)
        info = self._rows.get(item)
        if info is None or not info[0]:      # unknown row / the document root
            return
        self.tree.selection_set(item)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Add element (neighbor)", command=lambda: self._add_neighbor(item))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add_neighbor(self, item) -> None:
        path_tuple, _role, _editable = self._rows[item]
        try:
            if isinstance(path_tuple[-1], int):
                add_list_neighbor(self._doc, path_tuple)
            else:
                from tkinter import simpledialog
                new_key = simpledialog.askstring(
                    "Add element", f"New key (inserted after {path_tuple[-1]!r}):", parent=self)
                if not new_key or not new_key.strip():
                    return
                add_dict_neighbor(self._doc, path_tuple, new_key.strip())
        except ValueError as error:
            self._on_status(str(error))
            return
        self._set_dirty(True)
        self._rebuild()

    def _open_edit(self, item) -> None:
        self._close_edit()
        path_tuple, _role, _editable = self._rows[item]
        bbox = self.tree.bbox(item, "#1")
        if not bbox:
            return
        x, y, w, h = bbox
        edit = tk.Entry(self.tree)
        edit.insert(0, self._render(get_at(self._doc, path_tuple)))
        edit.select_range(0, "end")
        edit.place(x=x, y=y, width=w, height=h)
        edit.focus_set()
        edit.bind("<Return>", lambda _e: self._commit_edit(item, path_tuple, edit.get()))
        edit.bind("<Escape>", lambda _e: self._close_edit())
        edit.bind("<FocusOut>", lambda _e: self._close_edit())
        self._editbox = edit

    def _close_edit(self) -> None:
        if self._editbox is not None:
            try:
                self._editbox.destroy()
            except tk.TclError:
                pass
            self._editbox = None

    def _commit_edit(self, item, path_tuple, text: str) -> None:
        self._close_edit()
        set_at(self._doc, path_tuple, text)
        self.tree.set(item, "value", self._render(get_at(self._doc, path_tuple)))
        self._set_dirty(True)

    def _pick(self, item, path_tuple, role: str) -> None:
        current = str(get_at(self._doc, path_tuple) or "")
        base_dir = os.path.dirname(os.path.abspath(self._path))
        start = current if os.path.isabs(current) else os.path.normpath(os.path.join(base_dir, current))
        if role == "dir":
            chosen = filedialog.askdirectory(initialdir=start if os.path.isdir(start) else base_dir,
                                             parent=self)
        else:
            chosen = filedialog.askopenfilename(
                initialdir=os.path.dirname(start) if os.path.dirname(start) else base_dir,
                initialfile=os.path.basename(current), parent=self)
        if not chosen:
            return
        value = picked_value(current, os.path.normpath(chosen), base_dir)
        set_at(self._doc, path_tuple, value)
        self.tree.set(item, "value", value)
        self._set_dirty(True)

    def save(self) -> None:
        if self._doc is None:
            return
        try:
            dump_document(self._path, self._doc, self._kind)
        except Exception as error:  # noqa: BLE001
            self._on_status(f"save failed: {error}")
            return
        self._set_dirty(False)
        self._on_status(f"saved {os.path.basename(self._path)}")
