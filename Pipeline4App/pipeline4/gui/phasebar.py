"""The phase-button bar: classic `tk.Button`s (so they can take the ButtonsLayout fill colours - themed
ttk buttons can't take a custom background).

Built from the phase REGISTRY (`gui/phases.py`) - the single source of the phase order/labels (no
re-encoding). Each button calls `on_click(number, label)`. `set_enabled(False)` greys every button while a
run is in flight (the worker-thread busy guard). The chevron sub-phase dropdowns arrive with M4.
"""
from __future__ import annotations

import tkinter as tk

from pipeline4.gui import phases, theme


class PhaseBar(tk.Frame):
    def __init__(self, parent, on_click):
        super().__init__(parent, bg=theme.DARK_BG)
        self._buttons = []
        for phase in phases.PHASES:
            button = tk.Button(
                self, text=(f"{phase.number}  {phase.title}" if phase.number else phase.title),
                bg=theme.BUTTON_FILLS[phase.kind], fg=theme.BUTTON_FG[phase.kind],
                activebackground=theme.BUTTON_FILLS[phase.kind], activeforeground=theme.BUTTON_FG[phase.kind],
                relief="flat", borderwidth=0, padx=10, pady=6, cursor="hand2",
                command=lambda n=phase.number, lbl=phase.title: on_click(n, lbl),
            )
            button.pack(side="left", padx=3, pady=4)
            self._buttons.append(button)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable every phase button (greyed while a phase run is in flight)."""
        state = "normal" if enabled else "disabled"
        for button in self._buttons:
            button.configure(state=state)
