"""The phase-button bar: classic `tk.Button`s (so they can take the ButtonsLayout fill colours - themed
ttk buttons can't take a custom background).

A STATIC PL4 phase spec for now - the registry-driven version (mirroring PL3's generated bar) arrives
when the phase registry is ported. Each button calls `on_click(number, label)`; the host wires that to
whatever exists (today: a log line).
"""
from __future__ import annotations

import tkinter as tk

from pipeline4.gui import theme

# (number, label, kind). number 0 = the Run-all action; the rest are the 9 PL4 phases (PL3's ButtonsLayout).
PHASES = [
    (0, "Run Pipeline", "run"),
    (100, "Documents Validation", "phase"),
    (200, "Documents Fill Out", "phase"),
    (300, "Documents Staging", "phase"),
    (400, "Interfaces Generation", "phase"),
    (500, "Signals Mapping", "phase"),
    (600, "Diagnosis Mapping", "phase"),
    (700, "Hardware Generation", "phase"),
    (800, "Software Generation", "phase"),
    (900, "Reporting", "phase"),
]


class PhaseBar(tk.Frame):
    def __init__(self, parent, on_click):
        super().__init__(parent, bg=theme.DARK_BG)
        for number, label, kind in PHASES:
            button = tk.Button(
                self, text=(f"{number}  {label}" if number else label),
                bg=theme.BUTTON_FILLS[kind], fg=theme.BUTTON_FG[kind],
                activebackground=theme.BUTTON_FILLS[kind], activeforeground=theme.BUTTON_FG[kind],
                relief="flat", borderwidth=0, padx=10, pady=6, cursor="hand2",
                command=lambda n=number, lbl=label: on_click(n, lbl),
            )
            button.pack(side="left", padx=3, pady=4)
