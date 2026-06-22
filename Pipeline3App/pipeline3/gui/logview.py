"""logview.py - the colour-coded log pane (the pipeline's `emit` sink, rendered).

A read-only `tk.Text` with a vertical scrollbar, Monaspace font, and per-level colour tags
(theme.log_tags). `append(text)` infers the level from a leading `[LEVEL]` tag or a leading level
word (ERROR/WARNING/HALT/...), else INFO. Inserts must happen on the Tk main thread - the App drains
its worker queue into here via `root.after`.
"""
from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk

from pipeline3.gui import theme

_LEVELS = ("ERROR", "FAIL", "HALT", "WARNING", "PASS", "SKIP", "OK", "INFO", "SECTION")
_TAGGED = re.compile(r"^\s*\[(\w+)\]")          # "[ERROR] ..."
_LEADING = re.compile(r"^\s*(\w+)\b")           # "  ERROR ..." / "WARN ..."


def level_of(line: str) -> str:
    m = _TAGGED.match(line)
    word = (m.group(1) if m else (_LEADING.match(line).group(1) if _LEADING.match(line) else "")).upper()
    if word in _LEVELS:
        return word
    if word in ("WARN",):
        return "WARNING"
    if word in ("ORPHAN", "UNPLACED"):
        return "WARNING"
    return "INFO"


class LogView(ttk.Frame):
    def __init__(self, parent, pal: dict, font_family: str, **kw):
        super().__init__(parent, **kw)
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
        for level, cfg in theme.log_tags(pal["name"] == "dark", font_family).items():
            self.text.tag_configure(level, **cfg)

    def append(self, text: str, level: str | None = None) -> None:
        self.text.configure(state="normal")
        for line in str(text).splitlines() or [""]:
            self.text.insert("end", line + "\n", level or level_of(line))
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
