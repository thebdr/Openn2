"""The Files tab's TEMPLATE MODE for a `chain_reactions/templates.yaml` (C-025 - the template builder):
the Tk shell over src://pipeline5/workbench/template_doc.py (the Tk-free model + Session).

  - highlighting in two layers: YAML for the structure, the system's target language under the
    template constructs (@directives, @use references, {holes} and their expression tokens, {{ }});
  - LIVE squiggles (errors red, warnings amber) + a problems list - click one to jump to it. This is
    engine.lint: what a fire would report, found WITHOUT firing, in every branch, on every leg;
  - a CONTEXT BAR: a rule of the active reactions.csv + a source row of the Database its hook's fire
    gets (rebuilt in memory - see template_doc.Session);
  - a live PREVIEW: engine.preview - one fire of that rule for that row, nothing added or written;
  - AUTOCOMPLETE at the cursor from the rule's context.

THE EDITOR STAYS LIVE: once the Session is constructed (the config files read - no build), its WORK - a
reload, building a hook's Database (staging in memory), the settle and the cascade, the lint, the
preview, the completion context - runs on ONE worker thread, the newest request only; the Tk thread
parses, paints, reads the session's plain state (the rule list, whether a hook's Database is built)
and applies the newest result - one computed for an older request, or for a text edited since, is
dropped.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from pipeline5.workbench import syntax_highlight as highlight
from pipeline5.workbench import template_doc, theme
from pipeline5.workbench.completion_popup import NAVIGATION, CompletionPopup

_DEBOUNCE_MS = 250
_POLL_MS = 100
_SQUIGGLES = {"error": ("tp_error", "#ff6b6b", "#d63031"), "warning": ("tp_warning", "#fdcb6e", "#c05c00")}
_TRIGGERS = "$@._{"                                # besides letters/digits, the chars that complete


def _work(jobs: queue.Queue, results: queue.Queue, session) -> None:
    """The worker: the Session's work happens here, one batch at a time - a pending reload first, then
    only the NEWEST check (an older one - or one requested before that reload - is skipped). Results go
    back through `results`. A module-level function over the queues + the Session ONLY: it must hold no
    Tk object - one released last on this thread would take the Tcl interpreter down with it."""
    while True:
        pending = [jobs.get()]
        while True:
            try:
                pending.append(jobs.get_nowait())
            except queue.Empty:
                break
        if None in pending:
            return
        reloads = [job for job in pending if job[0] == "reload"]
        after = reloads[-1][1] if reloads else 0
        checks = [job for job in pending if job[0] == "check" and job[1] > after]
        if reloads:
            _kind, number, chosen = reloads[-1]
            try:
                session.reload()
                results.put(("labels", number, session.rule_labels(), chosen, None))
            except Exception as error:  # noqa: BLE001
                results.put(("labels", number, None, chosen, error))
        if checks:
            _kind, number, doc, rule, row = checks[-1]
            try:
                placed = session.check(doc, rule)
                count = session.row_count(rule, doc.templates) if rule is not None else 0
                shown = session.preview_text(doc, rule, row)
                context = session.context(rule, doc.templates)
                results.put(("check", number, (placed, count, shown, context, doc.text), None, None))
            except template_doc.StaleRule:
                pass                                    # over the rules a reload replaced: its labels come back and
                                                        # a fresh check follows (`_drain` -> `on_rule`)
            except Exception as error:  # noqa: BLE001 - a builder defect is shown, never raised
                results.put(("check", number, None, None, error))


class TemplateMode:
    def __init__(self, text: tk.Text, bar, lower, *, mode: str = "dark", session=None, path=None):
        self.text, self.mode = text, mode
        self.session = session if session is not None else template_doc.Session(path)
        self.doc = template_doc.parse("")
        self.placed: list = []
        self._items: dict = {}
        self._job = None                                   # the debounced refresh
        self._editing = False                              # an edit not yet sent to the worker
        self._jobs: queue.Queue = queue.Queue()            # requests for the worker
        self._results: queue.Queue = queue.Queue()         # what it computed, applied on the Tk thread
        self._request = 0                                  # the newest request's number (older = stale)
        self._context = template_doc.Context()             # the newest rule context (completions read it)

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
        threading.Thread(target=_work, args=(self._jobs, self._results, self.session), daemon=True,
                         name="template-builder").start()     # (it holds no Tk object - see _work)
        self._poll_job = self.text.after(_POLL_MS, self._poll)
        self.on_rule()

    def _on_destroy(self, event) -> None:
        if event.widget is self.text:
            for job in (self._job, self._poll_job):        # a pending refresh / poll must not outlive it
                if job:
                    self.text.after_cancel(job)
            self._job = self._poll_job = None
            self._jobs.put(None)                           # the worker ends

    # --- state ----------------------------------------------------------------------------------- #
    def rule(self):
        return self.session.rule(max(0, self.rule_box.current()))

    def row(self) -> int:
        try:
            return max(0, int(self.row_box.get()))
        except (TypeError, ValueError):
            return 0

    def on_rule(self) -> None:
        self._context = template_doc.Context()             # another rule's names are out of scope now
        self.refresh()

    def reload(self) -> None:
        """↻: the worker re-reads the rules and rebuilds the hook databases (after the build it may be
        running - never racing it), then the labels come back and a fresh check follows."""
        self._request += 1
        self._jobs.put(("reload", self._request, self.rule_box.get()))

    # --- the refresh: parse + paint here, check + preview on the worker ------------------------------ #
    def schedule(self) -> None:
        self._editing = True
        if self._job:
            self.text.after_cancel(self._job)
        self._job = self.text.after(_DEBOUNCE_MS, self._debounced)

    def _debounced(self) -> None:
        self._job = None
        self.refresh()

    def refresh(self) -> None:
        if self._job:                                      # a direct refresh supersedes a pending one
            self.text.after_cancel(self._job)
            self._job = None
        if not self.text.winfo_exists():
            return
        try:
            self.doc = template_doc.parse(self.text.get("1.0", "end-1c"))
            self._paint(template_doc.spans(self.doc, self.session.language))
        except Exception as error:  # noqa: BLE001 - a builder defect must never freeze the editor
            self._failed(error)
            return
        rule = self.rule()
        self._editing = False
        self._request += 1
        self._jobs.put(("check", self._request, self.doc, rule, self.row()))
        if rule is not None and not self.session.loaded(rule.fire_when):
            self._show_preview(f"building the Database the {rule.fire_when} fire gets (staging in memory, "
                               "nothing saved) - the rule's checks and preview follow...")

    def _poll(self) -> None:
        self._poll_job = None
        if not self.text.winfo_exists():
            return
        try:
            self._drain()
        except Exception as error:  # noqa: BLE001 - a builder defect must never stop the results
            self._failed(error)
        self._poll_job = self.text.after(_POLL_MS, self._poll)

    def _drain(self) -> None:
        """Apply what the worker computed: new rule labels (then a fresh check), and the NEWEST check -
        one for an older request, or for a text edited since it was sent, is dropped."""
        checks = []
        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            kind, _number, payload, chosen, error = result
            if kind == "labels":
                if error is not None:
                    self._failed(error)
                else:
                    self.rule_box.configure(values=payload)
                    self.rule_box.current(payload.index(chosen) if chosen in payload else 0)
                    self.on_rule()                           # a fresh check against the reloaded rules
            else:
                checks.append(result)
        newest = [r for r in checks if r[1] == self._request]
        if newest and not self._editing and self._for_this_text(newest[-1]):
            self._apply(newest[-1])                          # (positions of another text would be wrong)

    def _for_this_text(self, result) -> bool:
        """Whether `result` was computed for the text as it IS - an edit's <<Modified>> may not have run yet
        (its handler sets `_editing`), so the text itself is compared."""
        payload = result[2]
        return payload is None or payload[-1] == self.text.get("1.0", "end-1c")

    def _apply(self, result) -> None:
        _kind, _number, payload, _chosen, error = result
        if error is not None:
            self._failed(error)
            return
        self.placed, count, shown, self._context, _text = payload
        self._squiggle()
        self._fill_problems()
        self.row_box.configure(to=max(0, count - 1), state="normal" if count else "disabled")
        self._show_preview(shown)

    def _failed(self, error) -> None:
        self.summary.configure(text=f"template builder error: {type(error).__name__}")
        self._show_preview(f"the template builder failed: {type(error).__name__}: {error}")

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
        notes = list(self.session.notes)
        tail = f"  |  {notes[0]}" + (f" (+{len(notes) - 1} more)" if len(notes) > 1 else "") if notes else ""
        self.summary.configure(text=(f"{errors} error(s), {warnings} warning(s)" if self.placed
                                     else "no problems") + tail)

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

    # --- completion (the newest context - never a Session call on the Tk thread) ---------------------- #
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
        start, candidates = template_doc.completions(doc, at, self._context)
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
