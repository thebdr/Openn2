"""logview.py - the colour-coded, link-aware log pane (the pipeline's `emit` sink, rendered).

A read-only `tk.Text` with per-level colour tags (theme.log_tags). Two feeds:
- `append(text)` - plain progress strings (the worker `emit`): infers the level from a leading
  `[LEVEL]` tag or level word, else INFO; no links.
- `append_records(records, error_csv, resolve_doc)` - the STRUCTURED validation log
  (`render.render_records`). Each record carries the line text + the char spans of its `Sheet!Cell`
  cells and their workbook (`doc`/`doc2`). Each span becomes a clickable link (-> `on_link(doc, sheet,
  cell)`, which the App opens in the RIGHT workbook in Excel via COM); the leading `[FAIL]`/`[ERROR]`
  tag becomes an `errlink` opening the error-management CSV. Binding from the record (not by
  re-parsing text against "known sheets") is what makes cross-workbook links work and can't race.
Inserts must happen on the Tk main thread - the App drains its worker queue into here via `root.after`.
"""
from __future__ import annotations
import os
import re
import tkinter as tk
from tkinter import ttk

from pipeline3.gui import theme
from pipeline3.io.render import banner_lines

_LEVELS = ("ERROR", "FAIL", "HALT", "WARNING", "PASS", "SKIP", "OK", "INFO", "SECTION")
_TAGGED = re.compile(r"^\s*\[(\w+)\]")
_LEADING = re.compile(r"^\s*(\w+)\b")
# A finding's LogEntry level -> the theme colour tag (theme.log_tags keys).
_LEVEL_TAG = {"FAIL": "FAIL", "WARN": "WARNING", "INFO": "INFO", "PASS": "PASS",
              "SKIP": "SKIP", "ERROR": "ERROR", "OK": "OK", "HALT": "HALT"}


def level_of(line: str) -> str:
    m = _TAGGED.match(line) or _LEADING.match(line)
    word = (m.group(1) if m else "").upper()
    if word in _LEVELS:
        return word
    if word == "WARN":
        return "WARNING"
    if word in ("ORPHAN", "UNPLACED"):
        return "WARNING"
    return "INFO"


class LogView(ttk.Frame):
    def __init__(self, parent, pal: dict, font_family: str, on_link=None, **kw):
        super().__init__(parent, **kw)
        self.font_family = font_family
        self.on_link = on_link                  # on_link(doc, sheet, cell) -> open that workbook in Excel
        self._error_csv = None                  # the [FAIL]/[ERROR] errlink target (set per run)
        self._links = 0
        self.text = tk.Text(self, wrap="none", relief="flat", borderwidth=0,
                            background=pal["log_bg"], foreground=pal["log_fg"],
                            insertbackground=pal["fg"], font=(font_family, 10),
                            padx=8, pady=6, state="disabled")
        vs = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._accent = pal.get("accent", "#4ea1ff")
        self._retag()
        # the shared [FAIL]/[ERROR] -> error_management.csv link (underline only; keeps the level colour)
        self.text.tag_configure("errlink", underline=True)
        self.text.tag_bind("errlink", "<Button-1>", lambda _e: self._open_error_csv())
        self.text.tag_bind("errlink", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("errlink", "<Leave>", lambda _e: self.text.configure(cursor=""))

    # ---- theming --------------------------------------------------------- #
    def _retag(self):
        for level, cfg in theme.log_tags(self._dark(), self.font_family).items():
            self.text.tag_configure(level, **cfg)

    def _dark(self) -> bool:
        # the log bg is the theme bg; treat a dark-ish bg as dark mode for the level palette
        return self.text.cget("background") not in ("#ffffff", "#fafafa", "#fbfbfb")

    def retheme(self, pal: dict):
        self._accent = pal.get("accent", self._accent)
        self.text.configure(background=pal["log_bg"], foreground=pal["log_fg"], insertbackground=pal["fg"])
        self._retag()

    # ---- content --------------------------------------------------------- #
    def append(self, text: str, level: str | None = None) -> None:
        """A plain progress string (no links): level-colour each line."""
        self.text.configure(state="normal")
        for line in str(text).splitlines() or [""]:
            self.text.insert("end", line + "\n", level or level_of(line))
        self.text.see("end")
        self.text.configure(state="disabled")

    def append_records(self, records, error_csv_path=None, resolve_doc=None) -> None:
        """Append the structured validation log (`render.render_records`). Each link span becomes a
        clickable cell (-> on_link(doc, sheet, cell)); a `[FAIL]`/`[ERROR]` prefix opens
        `error_csv_path`. `resolve_doc` is unused here (the App resolves the workbook in on_link)."""
        self._error_csv = error_csv_path
        self.text.configure(state="normal")
        for rec in records:
            if rec.kind == "banner":
                for bl in banner_lines(rec.text):
                    self.text.insert("end", bl + "\n", "SECTION")
                continue
            start = self.text.index("end-1c")
            self.text.insert("end", rec.text + "\n", _LEVEL_TAG.get(rec.level, "INFO"))
            self._tag_errlink(start, rec)
            for span in rec.links:
                self._tag_link_span(start, span)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _tag_link_span(self, line_start: str, span) -> None:
        """Make the span at [start, end) a clickable link: a `Sheet!Cell` jumps to that cell; a label
        with no `!` (a cross-check miss) opens the workbook with no cell."""
        if not (self.on_link and span.start < span.end):
            return
        s, e = f"{line_start}+{span.start}c", f"{line_start}+{span.end}c"
        token = self.text.get(s, e)
        sheet, cell = token.split("!", 1) if "!" in token else ("", "")
        tag = f"link{self._links}"
        self._links += 1
        self.text.tag_add(tag, s, e)
        self.text.tag_configure(tag, foreground=self._accent, underline=True)
        self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.configure(cursor=""))
        self.text.tag_bind(tag, "<Button-1>",
                           lambda _e, d=span.doc, sh=sheet, c=cell: self.on_link(d, sh, c))

    def _tag_errlink(self, line_start: str, rec) -> None:
        """Tag the leading `[FAIL]`/`[ERROR]` token as the error_management.csv link."""
        if rec.level not in ("FAIL", "ERROR") or not self._error_csv:
            return
        end = f"{line_start}+{len(rec.level) + 2}c"          # "[" + level + "]"
        self.text.tag_add("errlink", line_start, end)

    def _open_error_csv(self) -> None:
        path = self._error_csv
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._links = 0
