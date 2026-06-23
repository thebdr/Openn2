"""logview.py - the colour-coded, link-aware log pane (the pipeline's `emit` sink, rendered).

A read-only `tk.Text` with a vertical scrollbar, Monaspace font, and per-level colour tags
(theme.log_tags). `append(text)` infers the level from a leading `[LEVEL]` tag or a leading level
word (ERROR/WARNING/HALT/...), else INFO, and makes any `<Sheet>!<Cell>` token of a KNOWN I/O-List
sheet a clickable link (-> `on_link(sheet, cell)`, which the App opens in Excel via COM). Inserts must
happen on the Tk main thread - the App drains its worker queue into here via `root.after`.
"""
from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk

from pipeline3.gui import theme

_LEVELS = ("ERROR", "FAIL", "HALT", "WARNING", "PASS", "SKIP", "OK", "INFO", "SECTION")
_TAGGED = re.compile(r"^\s*\[(\w+)\]")
_LEADING = re.compile(r"^\s*(\w+)\b")
_CELL = r"!([A-Z]{1,3}\d+)"


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
        self.on_link = on_link
        self._sheets: list = []
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
    def set_sheets(self, sheets) -> None:
        """The known I/O-List sheet names to turn into clickable Sheet!Cell links (longest first)."""
        self._sheets = sorted({s for s in sheets if s}, key=len, reverse=True)

    def append(self, text: str, level: str | None = None) -> None:
        self.text.configure(state="normal")
        for line in str(text).splitlines() or [""]:
            start = self.text.index("end-1c")
            self.text.insert("end", line + "\n", level or level_of(line))
            self._linkify(start, line)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _linkify(self, line_start: str, line: str) -> None:
        if not (self._sheets and self.on_link):
            return
        for sheet in self._sheets:
            for m in re.finditer(re.escape(sheet) + _CELL, line):
                cell = m.group(1)
                tag = f"link{self._links}"
                self._links += 1
                s = f"{line_start}+{m.start()}c"
                e = f"{line_start}+{m.end()}c"
                self.text.tag_add(tag, s, e)
                self.text.tag_configure(tag, foreground=self._accent, underline=True)
                self.text.tag_bind(tag, "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
                self.text.tag_bind(tag, "<Leave>", lambda _e: self.text.configure(cursor=""))
                self.text.tag_bind(tag, "<Button-1>",
                                   lambda _e, sh=sheet, c=cell: self.on_link(sh, c))

    def append_report(self, lines) -> None:
        """Append already-rendered report lines (render.render_lines): a `[LEVEL]`-prefixed entry gets
        its level colour; a PHASE banner (a title line + its `===` underline) is SECTION; Sheet!Cell
        tokens become clickable."""
        def _rule(s):
            return bool(s) and all(c == "=" for c in s)
        self.text.configure(state="normal")
        n = len(lines)
        for i, line in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < n else ""
            level = "SECTION" if (_rule(line) or _rule(nxt)) else level_of(line)
            start = self.text.index("end-1c")
            self.text.insert("end", line + "\n", level)
            self._linkify(start, line)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._links = 0
