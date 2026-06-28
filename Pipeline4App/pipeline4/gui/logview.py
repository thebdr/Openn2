"""The colour-coded, link-aware log pane - a read-only `tk.Text` (v+h scrollbars) with one tag per
severity level. Two feeds:
- `append(level, message)` - a plain progress/summary line (PHASE banner, PASS summary).
- `append_records(records)` - the STRUCTURED log (`io.render.render_records`): each RenderRec carries the
  line text + the char spans of its `Sheet!Cell` cells (with their workbook `doc`). Each span becomes a
  clickable link (-> `on_link(doc, sheet, cell)` -> open the workbook in Excel at the cell); a treatable
  line's leading `[LEVEL]` tag is an errlink (right-click -> `on_errtreat(uid, level)`). Binding from the
  record (not by re-parsing text) is what makes the cross-workbook links work and can't race.
Inserts happen on the Tk main thread (the App drains its worker queue into here via `root.after`).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pipeline4.gui import theme
from pipeline4.io.render import banner_lines

_ACCENT = theme.LOG_COLORS["PHASE"][0]            # the clickable-link colour
_TREATABLE = ("FAIL", "ERROR", "WARN")
_ALWAYS_SHOWN = ("PHASE", "FAIL", "ERROR")        # never hideable from the GUI (banners + the failures)


class LogView(ttk.Frame):
    def __init__(self, parent, shown_levels=None, on_link=None, on_errtreat=None, **kw):
        super().__init__(parent, **kw)
        self.shown_levels = set(shown_levels) if shown_levels is not None else set(theme.LOG_COLORS)
        self.on_link = on_link                    # on_link(doc, sheet, cell)
        self.on_errtreat = on_errtreat            # on_errtreat(uid, level)
        self._links = 0
        self._errs = 0

        self.text = tk.Text(self, wrap="none", relief="flat", borderwidth=0, state="disabled",
                            background=theme.DARK_BG, foreground=theme.DARK_FG,
                            insertbackground=theme.DARK_FG, font=theme.MONO_FONT, padx=8, pady=6)
        vs = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        for level, (color, bold) in theme.LOG_COLORS.items():
            self.text.tag_configure(level, foreground=color,
                                    font=(theme.MONO_FONT[0], theme.MONO_FONT[1], "bold" if bold else "normal"))
        self.text.tag_configure("errlink", underline=True)
        self.text.tag_bind("errlink", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("errlink", "<Leave>", lambda _e: self.text.configure(cursor=""))
        self._apply_elide()                       # hide the not-shown levels (lines are inserted, then elided)

    def append(self, level: str, message: str) -> None:
        """A plain (link-less) line - level-coloured. Inserted regardless of the shown set; a not-shown
        level's tag is ELIDED, so the Levels dropdown can show/hide it live."""
        level = (level or "INFO").upper()
        tag = level if level in theme.LOG_COLORS else "INFO"
        self.text.configure(state="normal")
        self.text.insert("end", f"{message}\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def append_records(self, records) -> None:
        """Append structured records (`io.render.render_records`): banners, level-coloured finding lines,
        clickable `Sheet!Cell` link spans, and a treatable line's errlink."""
        self.text.configure(state="normal")
        for rec in records:
            if rec.kind == "banner":
                for line in banner_lines(rec.text):
                    self.text.insert("end", line + "\n", "PHASE")
                continue
            start = self.text.index("end-1c")
            tag = rec.level if rec.level in theme.LOG_COLORS else "INFO"
            self.text.insert("end", rec.text + "\n", tag)
            self._tag_errlink(start, rec)
            for span in rec.links:
                self._tag_link_span(start, span)
        self.text.see("end")
        self.text.configure(state="disabled")

    def set_shown_levels(self, levels) -> None:
        """Set which log levels are visible (FAIL/ERROR/PHASE are always shown). Hides/shows in place via
        per-level elide - no re-render. The host persists the choice to app_config.yaml."""
        self.shown_levels = set(levels) | set(_ALWAYS_SHOWN)
        self._apply_elide()

    def _apply_elide(self) -> None:
        for level in theme.LOG_COLORS:
            self.text.tag_configure(level, elide=(level not in self.shown_levels and level not in _ALWAYS_SHOWN))

    def _tag_link_span(self, line_start, span) -> None:
        if not (self.on_link and span.doc and span.start < span.end):
            return                                # only a real-workbook (doc-bearing) span is a link
        s, e = f"{line_start}+{span.start}c", f"{line_start}+{span.end}c"
        token = self.text.get(s, e)
        sheet, cell = token.split("!", 1) if "!" in token else ("", "")
        tag = f"link{self._links}"
        self._links += 1
        self.text.tag_add(tag, s, e)
        self.text.tag_configure(tag, foreground=_ACCENT, underline=True)
        self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.configure(cursor=""))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda _e, d=span.doc, sh=sheet, c=cell: self.on_link(d, sh, c))

    def _tag_errlink(self, line_start, rec) -> None:
        """The leading `[LEVEL]` of a treatable line -> right-click to treat the finding (by uid)."""
        if rec.level not in _TREATABLE or not (self.on_errtreat and getattr(rec, "uid", "")):
            return
        end = f"{line_start}+{len(rec.level) + 2}c"            # "[" + level + "]"
        self.text.tag_add("errlink", line_start, end)
        tag = f"err{self._errs}"
        self._errs += 1
        self.text.tag_add(tag, line_start, end)
        self.text.tag_bind(tag, "<Button-3>", lambda e, u=rec.uid: self._err_menu(e, u))

    def _err_menu(self, event, uid: str) -> None:
        from pipeline4.core import treatments
        menu = tk.Menu(self.text, tearoff=0)
        for level in treatments.TREATMENTS:                   # fail / error / warn / skip / ignore
            menu.add_command(label=f"Treat as {level.upper()}", command=lambda lv=level: self.on_errtreat(uid, lv))
        menu.add_separator()
        menu.add_command(label="Clear treatment", command=lambda: self.on_errtreat(uid, ""))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._links = 0
        self._errs = 0
