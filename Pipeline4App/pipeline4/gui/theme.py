"""Theme for the PL4 GUI.

Applies **sv-ttk** (Sun Valley dark/light) when it's installed, with a graceful fallback to a plain ttk
theme so the window ALWAYS launches (no hard dependency on a theme package - we are testing). Exposes a
small palette the rest of the GUI reads: the phase-button fill colours (mirroring PL3's ButtonsLayout)
and the per-log-level colours. The phase buttons + the log pane are classic `tk` widgets (themed ttk
buttons can't take a custom background), so they use these explicit colours either way.
"""
from __future__ import annotations

import tkinter.font as tkfont
from tkinter import ttk

from pipeline4.gui import fonts

# Classic-tk-button fills (mirrors PL3's ButtonsLayout): run=pink, phase/action=white, open=light-blue,
# special=orange, chevron=mid-grey (the sub-phase dropdown opener), disabled=grey - with a readable
# foreground for each.
BUTTON_FILLS = {"run": "#e84393", "phase": "#f5f6fa", "action": "#dfe6e9",
                "open": "#74b9ff", "special": "#e67e22", "chevron": "#636e72", "disabled": "#b2bec3"}
BUTTON_FG = {"run": "#ffffff", "phase": "#2d3436", "action": "#2d3436",
             "open": "#1e272e", "special": "#ffffff", "chevron": "#f5f6fa", "disabled": "#636e72"}

# log level -> (foreground colour, bold?). FAIL (halt) is bold red; ERROR a softer red; DEBUG muted.
LOG_COLORS = {"PHASE": ("#74b9ff", True), "FAIL": ("#ff6b6b", True), "ERROR": ("#e17055", True),
              "WARN": ("#fdcb6e", False), "PASS": ("#55efc4", False), "INFO": ("#dfe6e9", False),
              "SKIP": ("#b2bec3", False), "DEBUG": ("#a29bfe", False)}

DARK_BG = "#1e1e1e"
DARK_FG = "#dfe6e9"
LIGHT_BG = "#ffffff"
LIGHT_FG = "#2d3436"
APP_FONT_SIZE = 11                 # the app-wide UI font size (Monaspace Neon Var)
# The app-wide monospace font: the bundled Monaspace Neon Var family at APP_FONT_SIZE. Resolved (the
# bundled TTF registered + the family confirmed) by `apply_theme`; the default here is a safe fallback
# for any pre-theme reference. The phase bar + log viewer read this; the chrome reads the named Tk fonts.
MONO_FONT = (fonts.FALLBACK, APP_FONT_SIZE)

# Light-mode log colours: same semantic palette but adjusted for a white background (WARN goes orange —
# yellow is invisible on white; INFO goes near-black instead of near-white).
LOG_COLORS_LIGHT = {
    "PHASE": ("#0984e3", True), "FAIL": ("#d63031", True), "ERROR": ("#e17055", True),
    "WARN": ("#e67e22", False), "PASS": ("#00b894", False), "INFO": ("#2d3436", False),
    "SKIP": ("#636e72", False), "DEBUG": ("#6c5ce7", False),
}


def bg_for(mode: str) -> str:
    return DARK_BG if mode == "dark" else LIGHT_BG


def fg_for(mode: str) -> str:
    return DARK_FG if mode == "dark" else LIGHT_FG


def log_colors_for(mode: str) -> dict:
    return LOG_COLORS if mode == "dark" else LOG_COLORS_LIGHT


def phasebar_bg(mode: str) -> str:
    """The phase-bar frame background: dark bg in dark mode (buttons pop); a medium grey in light mode
    so the white/light oracle button fills still stand out against the bar."""
    return DARK_BG if mode == "dark" else "#b2bec3"


def apply_theme(root, mode: str = "dark") -> str:
    """Apply sv-ttk if installed (-> returns 'sv-ttk'); otherwise a plain ttk theme (-> 'fallback'), then
    make the bundled Monaspace Neon Var the app-wide UI font at APP_FONT_SIZE. NEVER raises - the window
    must come up even with no theme package / no bundled font available.

    Does NOT touch the Windows title bar: `darktitle.apply` calls `update_idletasks()`, which - if run
    here, before the App has built its widgets - flushes sv-ttk's theme application against an empty
    window so the later-created ttk widgets never pick up the theme (toolbar/notebook/status stay light).
    The App applies the title bar separately, AFTER its widgets exist (mirrors PL3)."""
    backend = "fallback"
    try:
        import sv_ttk
        sv_ttk.set_theme(mode)
        backend = "sv-ttk"
    except Exception:  # noqa: BLE001  - missing package / any init failure -> fall back, still launch
        try:
            ttk.Style(root).theme_use("clam")
        except Exception:  # noqa: BLE001
            pass
        try:
            root.configure(bg=DARK_BG if mode == "dark" else "#f5f6fa")
        except Exception:  # noqa: BLE001
            pass
    _apply_app_font(root)
    return backend


def _apply_app_font(root) -> None:
    """Register the bundled Monaspace TTF + make it the app-wide UI font at APP_FONT_SIZE: point the named
    Tk fonts (every ttk/tk widget inherits these) at the resolved family, and update the module MONO_FONT
    so the classic-tk phase bar + the log viewer pick up the same family. Falls back to Consolas if the
    bundled font can't be registered (so the app still launches)."""
    global MONO_FONT
    fonts.register()
    family = fonts.family(root)
    MONO_FONT = (family, APP_FONT_SIZE)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont"):
        try:
            tkfont.nametofont(name).configure(family=family, size=APP_FONT_SIZE)
        except Exception:  # noqa: BLE001
            pass
