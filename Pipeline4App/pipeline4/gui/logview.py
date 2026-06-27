"""A colour-coded log pane: a read-only scrolled Text with one tag per log level.

`append(level, message)` adds a coloured line; `clear()` empties it. This is a simpler PL4 take on
PL3's logview - line-based, no structured records / clickable links yet. Those arrive together with the
LogEntry model when the phases are ported and start emitting real findings; the GUI is here first so the
plumbing exists to receive them.
"""
from __future__ import annotations

from tkinter import scrolledtext

from pipeline4.gui import theme


class LogView(scrolledtext.ScrolledText):
    def __init__(self, parent, shown_levels=None):
        super().__init__(parent, wrap="none", height=20, state="disabled", borderwidth=0,
                         bg=theme.DARK_BG, fg=theme.DARK_FG, insertbackground=theme.DARK_FG,
                         font=theme.MONO_FONT)
        # the levels this pane displays (the set from config.load_app_ui); None -> every coloured level.
        self.shown_levels = set(shown_levels) if shown_levels is not None else set(theme.LOG_COLORS)
        for level, (color, bold) in theme.LOG_COLORS.items():
            self.tag_configure(level, foreground=color,
                               font=(theme.MONO_FONT[0], theme.MONO_FONT[1], "bold" if bold else "normal"))

    def append(self, level: str, message: str) -> None:
        level = (level or "INFO").upper()
        if level not in self.shown_levels:           # the app_config.yaml log-level display filter
            return
        tag = level if level in theme.LOG_COLORS else "INFO"
        self.configure(state="normal")
        self.insert("end", f"{message}\n", tag)
        self.see("end")
        self.configure(state="disabled")

    def clear(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")
