"""Theme for the PL4 GUI.

Applies **sv-ttk** (Sun Valley dark/light) when it's installed, with a graceful fallback to a plain ttk
theme so the window ALWAYS launches (no hard dependency on a theme package - we are testing). Exposes a
small palette the rest of the GUI reads: the phase-button fill colours (mirroring PL3's ButtonsLayout)
and the per-log-level colours. The phase buttons + the log pane are classic `tk` widgets (themed ttk
buttons can't take a custom background), so they use these explicit colours either way.
"""
from __future__ import annotations

from tkinter import ttk

# Classic-tk-button fills (mirrors PL3's ButtonsLayout): run=pink, phase/action=white, open=light-blue,
# special=orange, disabled=grey - with a readable foreground for each.
BUTTON_FILLS = {"run": "#e84393", "phase": "#f5f6fa", "action": "#dfe6e9",
                "open": "#74b9ff", "special": "#e67e22", "disabled": "#b2bec3"}
BUTTON_FG = {"run": "#ffffff", "phase": "#2d3436", "action": "#2d3436",
             "open": "#1e272e", "special": "#ffffff", "disabled": "#636e72"}

# log level -> (foreground colour, bold?)
LOG_COLORS = {"PHASE": ("#74b9ff", True), "ERROR": ("#ff6b6b", True), "FAIL": ("#ff6b6b", True),
              "WARN": ("#fdcb6e", False), "PASS": ("#55efc4", False), "INFO": ("#dfe6e9", False),
              "SKIP": ("#b2bec3", False)}

DARK_BG = "#1e1e1e"
DARK_FG = "#dfe6e9"
MONO_FONT = ("Consolas", 10)


def apply_theme(root, mode: str = "dark") -> str:
    """Apply sv-ttk if installed (-> returns 'sv-ttk'); otherwise a plain ttk theme (-> 'fallback').
    NEVER raises - the window must come up even with no theme package available."""
    try:
        import sv_ttk
        sv_ttk.set_theme(mode)
        return "sv-ttk"
    except Exception:  # noqa: BLE001  - missing package / any init failure -> fall back, still launch
        try:
            ttk.Style(root).theme_use("clam")
        except Exception:  # noqa: BLE001
            pass
        try:
            root.configure(bg=DARK_BG if mode == "dark" else "#f5f6fa")
        except Exception:  # noqa: BLE001
            pass
        return "fallback"
