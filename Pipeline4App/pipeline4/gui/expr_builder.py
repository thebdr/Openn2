"""The ƒx Expression Builder (UI_REFRESH_PLAN H): author a `core/expr` expression or render template
with LIVE syntax highlighting (`expr.tokens`), LIVE lint squiggles (`expr.check`/`check_template`),
autocomplete ($columns of the chosen SSOT table, function/keyword names, table names), and a LIVE
preview evaluated against a real row of the SSOT Database. The `?` opens the guide's `expressions`
section when the help window is available.

The data half (CSV -> decoded rows, ctx building, the word-before-cursor scan) is Tk-free and tested;
the dialog is the Tk shell over it.
"""
from __future__ import annotations

import glob
import json
import os
import tkinter as tk
from tkinter import ttk

from pipeline4.core import config, expr
from pipeline4.gui import theme

_ROW_CAP = 500                 # rows loaded per table (an authoring aid, not a browser)
_DEBOUNCE_MS = 150

# tag -> (dark, light) editor colours; 'error' additionally underlines.
_TAG_COLORS = {
    "field":     ("#74b9ff", "#0055cc"),
    "func":      ("#a29bfe", "#7040a0"),
    "data_func": ("#a29bfe", "#7040a0"),
    "keyword":   ("#e67e22", "#b3541e"),
    "string":    ("#55efc4", "#1a7e1a"),
    "regex":     ("#ff7675", "#b33939"),
    "number":    ("#fdcb6e", "#c05c00"),
    "error":     ("#ff6b6b", "#d63031"),
    "lint":      ("#ff6b6b", "#d63031"),
}


# --- the Tk-free data half ------------------------------------------------------------------------ #
def decode_cell(cell: str):
    """A best-effort JSON decode for an SSOT cell (the codec stores object/list cells as their JSON
    string): '{..}'/'[..]' parse to the object so `$type.in_diag` drills work in the preview; anything
    else stays the raw string."""
    text = str(cell)
    if text[:1] in "{[":
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def load_tables(db_dir: str) -> dict:
    """{table: (columns, rows)} from `Database/*.csv`, cells decoded, capped at _ROW_CAP rows each.
    Lenient like the explorer: an unreadable/empty table is skipped."""
    import csv
    out = {}
    for path in sorted(glob.glob(os.path.join(db_dir or "", "*.csv"))):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
                if not header or len(set(header)) != len(header):
                    continue
                rows = []
                for raw in reader:
                    if len(rows) >= _ROW_CAP:
                        break
                    padded = (raw + [""] * len(header))[:len(header)]
                    rows.append({c: decode_cell(v) for c, v in zip(header, padded)})
        except OSError:
            continue
        out[name] = (list(header), rows)
    return out


def build_ctx(tables: dict, name: str, index: int) -> dict:
    """The eval ctx: the chosen row's fields + `_db` (EVERY loaded table) so the data functions
    (where/lookup/count/...) work in the preview."""
    columns, rows = tables.get(name) or ([], [])
    row = rows[index] if 0 <= index < len(rows) else {c: "" for c in columns}
    ctx = dict(row)
    ctx["_db"] = {t: r for t, (_c, r) in tables.items()}
    return ctx


def word_before(text: str, pos: int) -> tuple:
    """(word, start) - the $field / identifier fragment ending at `pos` (the autocomplete stem);
    ('', pos) when the cursor doesn't follow one."""
    i = pos
    while i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_.$"):
        i -= 1
    word = text[i:pos]
    if word.startswith("$") or (word and (word[0].isalpha() or word[0] == "_")):
        return word, i
    return "", pos


def completions(word: str, columns, tables) -> list:
    """The candidates for `word`: '$stem' -> the table columns; an identifier stem -> functions +
    keywords + table names (prefix-matched, case-insensitive)."""
    if word.startswith("$"):
        stem = word[1:].lower()
        return [f"${c}" for c in columns if c.lower().startswith(stem)]
    stem = word.lower()
    if not stem:
        return []
    pool = list(expr.function_names()) + ["and", "or", "not", "in"] + sorted(tables)
    return [w for w in pool if w.lower().startswith(stem) and w.lower() != stem]


# --- the dialog ------------------------------------------------------------------------------------ #
class ExprBuilder(tk.Toplevel):
    def __init__(self, parent, mode: str = "dark"):
        super().__init__(parent)
        self.title("ƒx Expression Builder")
        self.geometry("760x460")
        self._mode = mode
        self._job = None
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._tables = load_tables(config.database_dir())

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(bar, text="Surface:").pack(side="left")
        self._surface = tk.StringVar(value="test")
        for value, label in (("test", "test (predicate)"), ("evaluate", "evaluate"), ("render", "render {holes}")):
            ttk.Radiobutton(bar, text=label, value=value, variable=self._surface,
                            command=self._schedule).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="   Table:").pack(side="left")
        self._table = ttk.Combobox(bar, width=22, state="readonly", values=sorted(self._tables))
        self._table.pack(side="left", padx=2)
        self._table.bind("<<ComboboxSelected>>", lambda _e: self._on_table())
        ttk.Label(bar, text="Row:").pack(side="left", padx=(8, 2))
        self._row = tk.Spinbox(bar, from_=0, to=0, width=6, command=self._schedule)
        self._row.pack(side="left")
        ttk.Button(bar, text="?", width=3, command=self._open_guide).pack(side="right")

        self.editor = tk.Text(self, height=4, wrap="none", undo=True,
                              background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                              insertbackground=theme.fg_for(mode), font=theme.MONO_FONT)
        self.editor.pack(side="top", fill="x", padx=8)
        self.editor.bind("<KeyRelease>", self._on_key)
        self.editor.bind("<Escape>", lambda _e: self._close_popup())
        self.editor.bind("<Button-1>", lambda _e: self._close_popup(), "+")
        self._configure_tags()

        self._lint = ttk.Label(self, text="", anchor="w")
        self._lint.pack(side="top", fill="x", padx=10, pady=(2, 0))

        frame = ttk.Frame(self)
        frame.pack(side="top", fill="both", expand=True, padx=8, pady=(4, 8))
        ttk.Label(frame, text="Preview (against the chosen row):").pack(side="top", anchor="w")
        self.preview = tk.Text(frame, height=8, wrap="word", state="disabled",
                               background=theme.bg_for(mode), foreground=theme.fg_for(mode),
                               font=theme.MONO_FONT)
        self.preview.pack(side="top", fill="both", expand=True)

        if self._tables:
            first = "signals" if "signals" in self._tables else sorted(self._tables)[0]
            self._table.set(first)
            self._on_table()
        else:
            self._show_preview("no Database tables found - run a phase first")
        self.bind("<Destroy>", lambda e: self._close_popup() if e.widget is self else None)

    # --- context ------------------------------------------------------------------------------- #
    def _columns(self) -> list:
        entry = self._tables.get(self._table.get())
        return entry[0] if entry else []

    def _on_table(self) -> None:
        entry = self._tables.get(self._table.get())
        rows = entry[1] if entry else []
        self._row.configure(to=max(0, len(rows) - 1))
        self._schedule()

    def _ctx_scope(self) -> tuple:
        ctx = build_ctx(self._tables, self._table.get(), self._row_index())
        return ctx, expr.Scope(self._columns())

    def _row_index(self) -> int:
        try:
            return int(self._row.get())
        except (TypeError, ValueError):
            return 0

    # --- editing / refresh ----------------------------------------------------------------------- #
    def _on_key(self, event) -> None:
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape") and self._popup:
            return                                  # the popup navigation handled its own keys
        self._schedule()
        self._autocomplete()

    def _schedule(self) -> None:
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(_DEBOUNCE_MS, self._refresh)

    def _refresh(self) -> None:
        self._job = None
        text = self.editor.get("1.0", "end-1c")
        for tag in _TAG_COLORS:
            self.editor.tag_remove(tag, "1.0", "end")
        for kind, s, e in expr.tokens(text):
            if kind in _TAG_COLORS:
                self.editor.tag_add(kind, f"1.0+{s}c", f"1.0+{e}c")
        ctx, scope = self._ctx_scope()
        surface = self._surface.get()
        issues = (expr.check_template(text, scope) if surface == "render"
                  else expr.check(text, scope))
        for issue in issues:
            self.editor.tag_add("lint", f"1.0+{issue.start}c", f"1.0+{issue.end}c")
        self._lint.configure(text="  |  ".join(i.message for i in issues[:3]))
        if issues:
            self._show_preview("(fix the expression to preview)")
            return
        try:
            if surface == "test":
                result = expr.test(text, ctx, scope)
            elif surface == "evaluate":
                result = expr.evaluate(text, ctx, scope) if text.strip() else ""
            else:
                result = expr.render(text, ctx, scope)
            self._show_preview(repr(result) if not isinstance(result, str) else result or "(empty)")
        except Exception as error:  # noqa: BLE001 - a runtime error IS the preview
            self._show_preview(f"error: {error}")

    def _show_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _configure_tags(self) -> None:
        dark = self._mode == "dark"
        for tag, (dark_color, light_color) in _TAG_COLORS.items():
            kwargs = {"foreground": dark_color if dark else light_color}
            if tag in ("error", "lint"):
                kwargs["underline"] = True
            self.editor.tag_configure(tag, **kwargs)
        self.editor.tag_raise("lint")

    # --- autocomplete ---------------------------------------------------------------------------- #
    def _autocomplete(self) -> None:
        self._close_popup()
        text = self.editor.get("1.0", "end-1c")
        pos = len(self.editor.get("1.0", "insert"))
        word, start = word_before(text, pos)
        cands = completions(word, self._columns(), self._tables) if word else []
        if not cands:
            return
        bbox = self.editor.bbox("insert")
        if not bbox:
            return
        x = self.editor.winfo_rootx() + bbox[0]
        y = self.editor.winfo_rooty() + bbox[1] + bbox[3]
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        listbox = tk.Listbox(popup, height=min(8, len(cands)), font=theme.MONO_FONT,
                             background=theme.bg_for(self._mode), foreground=theme.fg_for(self._mode))
        for c in cands[:40]:
            listbox.insert("end", c)
        listbox.selection_set(0)
        listbox.pack()
        popup.geometry(f"+{x}+{y}")
        self._popup, self._listbox = popup, listbox

        def accept(_e=None):
            sel = listbox.get(listbox.curselection() or 0)
            self._close_popup()
            self.editor.delete(f"1.0+{start}c", "insert")
            self.editor.insert("insert", sel)
            self._schedule()
            return "break"

        def move(delta):
            cur = (listbox.curselection() or (0,))[0]
            new = max(0, min(listbox.size() - 1, cur + delta))
            listbox.selection_clear(0, "end")
            listbox.selection_set(new)
            listbox.see(new)
            return "break"

        listbox.bind("<Double-1>", accept)
        self.editor.bind("<Return>", lambda e: accept() if self._popup else None)
        self.editor.bind("<Tab>", lambda e: accept() if self._popup else None)
        self.editor.bind("<Down>", lambda e: move(1) if self._popup else None)
        self.editor.bind("<Up>", lambda e: move(-1) if self._popup else None)

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = self._listbox = None
        try:                                       # the dialog may be mid-teardown (editor already gone)
            if self.editor.winfo_exists():
                for seq in ("<Return>", "<Tab>", "<Down>", "<Up>"):
                    self.editor.unbind(seq)
        except tk.TclError:
            pass

    def _open_guide(self) -> None:
        try:
            from pipeline4.gui import helpwin
            helpwin.open_section(self, "expressions")
        except Exception:  # noqa: BLE001 - the guide ships with step I; degrade politely
            self._show_preview("the guide window is not available yet - see docs/guide/expressions.md")
