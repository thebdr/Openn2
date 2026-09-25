"""The Files tab's TEMPLATE MODE for a `chain_reactions/templates.yaml` (P-012 - the template builder):
the Tk shell over src://pipeline5/workbench/template_doc.py (the Tk-free model + Session).

  - highlighting in two layers: YAML for the structure, the target language (SCL) under the template
    constructs (@directives, @use references, {holes} and their expression tokens, {{ }} braces);
  - LIVE squiggles (errors red, warnings amber) + a problems list - click one to jump to it. This is
    engine.lint: what a fire would report, found WITHOUT firing, in every branch;
  - a CONTEXT BAR: a rule of the active reactions.csv + a source row of its hook's Database;
  - a live PREVIEW: engine.preview - one fire of that rule for that row, nothing added or written;
  - AUTOCOMPLETE at the cursor from the rule's context (its columns, loop vars, _params keys,
    templates, tables, directives, functions).
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from pipeline5.workbench import syntax_highlight as highlight
from pipeline5.workbench import template_doc, theme
from pipeline5.workbench.completion_popup import NAVIGATION, CompletionPopup

_DEBOUNCE_MS = 250
_SQUIGGLES = {"error": ("tp_error", "#ff6b6b", "#d63031"), "warning": ("tp_warning", "#fdcb6e", "#c05c00")}
_TRIGGERS = "$@._{"                                # besides letters/digits, the chars that complete


class TemplateMode:
    def __init__(self, text: tk.Text, bar, lower, *, mode: str = "dark", session=None, path=None):
        self.text, self.mode = text, mode
        self.session = session if session is not None else template_doc.Session(path)
        self.doc = template_doc.parse("")
        self.placed: list = []
        self._items: dict = {}
        self._job = None
        self._loading: set = set()                         # hooks whose Database a worker is building

        ttk.Label(bar, text="Rule:").pack(side="left")
        self.rule_box = ttk.Combobox(bar, state="readonly", width=52, values=self.session.rule_labels())
        self.rule_box.current(0)
        self.rule_box.pack(side="left", padx=(2, 8))
        self.rule_box.bind("<<ComboboxSelected>>", lambda _e: self.on_rule())
        ttk.Label(bar, text="Row:").pack(side="left")
        self.row_box = tk.Spinbox(bar, from_=0, to=0, width=6, command=self.schedule)
        self.row_box.pack(side="left", padx=(2, 6))
        self.row_box.bind("<KeyRelease>", lambda _e: self.schedule())
        ttk.Button(bar, text="↻ Reload rules + data", command=self.reload).pack(side="left", padx=(4, 0))
        self.summary = ttk.Label(bar, text="")
        self.summary.pack(side="right")

        split = ttk.Panedwindow(lower, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split)
        split.add(left, weight=1)
        self.problems = ttk.Treeview(left, columns=("where", "problem"), show="headings", height=6)
        self.problems.heading("where", text="Where")
        self.problems.heading("problem", text="Problem (what a fire would report)")
        self.problems.column("where", width=180, stretch=False)
        self.problems.column("problem", width=440)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.problems.yview)
        self.problems.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.problems.pack(side="left", fill="both", expand=True)
        self.problems.bind("<<TreeviewSelect>>", self._jump)
        right = ttk.Frame(split)
        split.add(right, weight=1)
        ttk.Label(right, text="Preview - one fire for the chosen row (nothing is written):").pack(anchor="w")
        self.preview = tk.Text(right, height=8, wrap="none", state="disabled", relief="flat",
                               font=theme.MONO_FONT, background=theme.bg_for(mode), foreground=theme.fg_for(mode))
        self.preview.pack(fill="both", expand=True)

        self.configure_tags()
        self.popup = CompletionPopup(text, mode, on_accept=self.schedule)
        text.bind("<KeyRelease>", self._on_key, "+")
        text.bind("<Destroy>", self._on_destroy, "+")
        self.on_rule()

    def _on_destroy(self, event) -> None:
        if event.widget is self.text and self._job:        # a pending refresh must not outlive it
            self.text.after_cancel(self._job)
            self._job = None

    # --- state ----------------------------------------------------------------------------------- #
    def rule(self):
        return self.session.rule(max(0, self.rule_box.current()))

    def row(self) -> int:
        try:
            return max(0, int(self.row_box.get()))
        except (TypeError, ValueError):
            return 0

    def on_rule(self) -> None:
        self.refresh()

    def _ready(self, rule) -> bool:
        """The rule's Database is built - else a worker builds it (staging in memory can take a while on
        a big project) and the refresh follows when it is done."""
        if self.session.ready(rule):
            return True
        if rule.fire_when not in self._loading:
            self._loading.add(rule.fire_when)
            threading.Thread(target=self.session.base, args=(rule.fire_when,), daemon=True).start()
            self.text.after(150, self._poll)
        return False

    def _poll(self) -> None:
        if not self.text.winfo_exists():
            return
        if any(not self.session.loaded(hook) for hook in self._loading):
            self.text.after(150, self._poll)
            return
        self._loading.clear()
        self.refresh()

    def reload(self) -> None:
        chosen = self.rule_box.get()
        self.session.reload()
        labels = self.session.rule_labels()
        self.rule_box.configure(values=labels)
        self.rule_box.current(labels.index(chosen) if chosen in labels else 0)
        self.on_rule()

    # --- the refresh: parse -> paint -> lint -> preview ---------------------------------------------- #
    def schedule(self) -> None:
        if self._job:
            self.text.after_cancel(self._job)
        self._job = self.text.after(_DEBOUNCE_MS, self.refresh)

    def refresh(self) -> None:
        self._job = None
        if not self.text.winfo_exists():
            return
        try:
            self._refresh()
        except Exception as error:  # noqa: BLE001 - a builder defect must never freeze the editor
            self.summary.configure(text=f"template builder error: {type(error).__name__}")
            self._show_preview(f"the template builder failed: {type(error).__name__}: {error}")

    def _refresh(self) -> None:
        self.doc = template_doc.parse(self.text.get("1.0", "end-1c"))
        self._paint(template_doc.spans(self.doc, self.session.language))
        rule = self.rule()
        ready = self._ready(rule)
        self.placed = self.session.check(self.doc, rule if ready else None)
        self._squiggle()
        self._fill_problems()
        count = self.session.row_count(rule, self.doc.templates) if ready else 0
        self.row_box.configure(to=max(0, count - 1), state="normal" if count else "disabled")
        if not ready:
            self._show_preview(f"building the Database the {rule.fire_when} fire gets (staging in memory, "
                               "nothing saved) - the rule's checks and preview follow...")
            return
        self._show_preview(self.session.preview_text(self.doc, rule, self.row()))

    def _paint(self, spans) -> None:
        for tag in list(highlight.COLORS) + list(template_doc.TAG_COLORS):
            self.text.tag_remove(tag, "1.0", "end")
        for tag, start, end in spans:
            self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")

    def _squiggle(self) -> None:
        for tag, _dark, _light in _SQUIGGLES.values():
            self.text.tag_remove(tag, "1.0", "end")
        for placed in self.placed:
            if placed.start is not None:
                tag = _SQUIGGLES.get(placed.severity, _SQUIGGLES["error"])[0]
                self.text.tag_add(tag, f"1.0+{placed.start}c", f"1.0+{max(placed.end, placed.start + 1)}c")

    def _fill_problems(self) -> None:
        self.problems.delete(*self.problems.get_children())
        self._items = {}
        for placed in self.placed:
            mark = "✖" if placed.severity == "error" else "⚠"
            item = self.problems.insert("", "end", values=(f"{mark} {placed.label}", placed.message),
                                        tags=(placed.severity,))
            self._items[item] = placed
        errors = sum(p.severity == "error" for p in self.placed)
        warnings = len(self.placed) - errors
        count = len(self.session.notes)
        notes = f"  |  {self.session.notes[0]}" + (f" (+{count - 1} more)" if count > 1 else "") if count else ""
        self.summary.configure(text=(f"{errors} error(s), {warnings} warning(s)" if self.placed
                                     else "no problems") + notes)

    def _show_preview(self, content: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", content)
        self.preview.configure(state="disabled")

    def _jump(self, _event=None) -> None:
        selected = self.problems.selection()
        placed = self._items.get(selected[0]) if selected else None
        if placed is None or placed.start is None:
            return
        start, end = f"1.0+{placed.start}c", f"1.0+{max(placed.end, placed.start + 1)}c"
        self.text.mark_set("insert", start)
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", start, end)
        self.text.see(start)
        self.text.focus_set()

    # --- completion -------------------------------------------------------------------------------- #
    def _on_key(self, event) -> None:
        if event.keysym in NAVIGATION:
            if not self.popup.is_open or event.keysym == "Escape":
                self.popup.close()
            return
        char = event.char or ""
        if not char or not (char.isalnum() or char in _TRIGGERS):
            self.popup.close()
            return
        if str(self.text.cget("state")) == "disabled":
            return
        at = len(self.text.get("1.0", "insert"))
        doc = template_doc.parse(self.text.get("1.0", "end-1c"))     # the typed char included
        rule = self.rule()
        context = self.session.context(rule if self.session.ready(rule) else None, doc.templates)
        start, candidates = template_doc.completions(doc, at, context)
        self.popup.show(candidates, f"1.0+{start}c")

    # --- theme ------------------------------------------------------------------------------------------- #
    def configure_tags(self) -> None:
        dark = self.mode == "dark"
        highlight.configure_tags(self.text, self.mode)
        for tag, (dark_color, light_color) in template_doc.TAG_COLORS.items():
            self.text.tag_configure(tag, foreground=dark_color if dark else light_color)
            self.text.tag_raise(tag)                       # the template layer over the language layers
        for tag, dark_color, light_color in _SQUIGGLES.values():
            try:
                self.text.tag_configure(tag, underline=True, underlinefg=dark_color if dark else light_color)
            except tk.TclError:                            # a Tk without -underlinefg
                self.text.tag_configure(tag, underline=True)
            self.text.tag_raise(tag)
        for severity, (_tag, dark_color, light_color) in _SQUIGGLES.items():
            self.problems.tag_configure(severity, foreground=dark_color if dark else light_color)

    def set_theme(self, mode: str) -> None:
        self.mode, self.popup.mode = mode, mode
        self.preview.configure(background=theme.bg_for(mode), foreground=theme.fg_for(mode))
        self.configure_tags()
