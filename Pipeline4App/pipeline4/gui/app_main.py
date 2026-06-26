"""The PL4 operator window: a toolbar, the phase-button bar, and a log viewer.

The backend isn't ported yet, so this is the testable SHELL the user asked for early (gui-less PL3 builds
hid integration problems until the GUI landed late). Phase buttons are wired to the log - clicking one
logs a line - so the plumbing (button -> handler -> log) is exercised now and each phase is wired into
this same hook as it gets ported. It launches even with no theme package and survives a button that does
nothing (`_on_phase` is wrapped so a future not-yet-ready handler can't take the window down).
"""
from __future__ import annotations

import tkinter as tk
import traceback
from tkinter import ttk

from pipeline4.gui import theme
from pipeline4.gui.logview import LogView
from pipeline4.gui.phasebar import PhaseBar

APP_TITLE = "Pipeline4 - SSOT database build (testing shell)"


class App:
    def __init__(self, root):
        self.root = root
        self.mode = "dark"
        root.title(APP_TITLE)
        root.geometry("1180x720")
        backend = theme.apply_theme(root, self.mode)

        toolbar = ttk.Frame(root)
        toolbar.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(toolbar, text="PIPELINE4", font=("Consolas", 13, "bold")).pack(side="left", padx=(2, 14))
        ttk.Button(toolbar, text="Theme", command=self._toggle_theme).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear Log", command=self._clear).pack(side="left", padx=2)
        self._backend_label = ttk.Label(toolbar, text=f"theme: {backend}")
        self._backend_label.pack(side="right", padx=2)

        self.phasebar = PhaseBar(root, self._on_phase)
        self.phasebar.pack(side="top", fill="x", padx=8, pady=2)

        self.log = LogView(root)
        self.log.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.status = ttk.Label(root, text="Ready", anchor="w", relief="sunken")
        self.status.pack(side="bottom", fill="x")

        self.log.append("PHASE", "Pipeline4 - SSOT database build (testing shell)")
        self.log.append("INFO", f"theme backend: {backend}")
        self.log.append("INFO", "The backend isn't wired yet - phase buttons just log. We are testing the GUI.")

    def _on_phase(self, number, label):
        try:
            if number == 0:
                self.log.append("PHASE", "Run Pipeline (all phases)")
            else:
                self.log.append("PHASE", f"{number} {label}")
            self.log.append("WARN", f"  -> phase {number or 'ALL'} not implemented yet")
            self.status.configure(text=f"clicked: {label}")
        except Exception:  # noqa: BLE001  - a not-yet-ready handler must never take the window down
            self.log.append("ERROR", f"handler for {label} crashed:\n{traceback.format_exc()}")

    def _toggle_theme(self):
        self.mode = "light" if self.mode == "dark" else "dark"
        backend = theme.apply_theme(self.root, self.mode)
        self._backend_label.configure(text=f"theme: {backend}")
        self.log.append("INFO", f"theme -> {self.mode}")

    def _clear(self):
        self.log.clear()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
