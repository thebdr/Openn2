"""Theme for the PL4 GUI - ONE semantic token table per mode + native ttk styling over `clam`.

Rebuilt from scratch (the GUI-refresh Step B): the previous sv-ttk backend was MEASURED as the UI-wide
paint drag on the target machine (a VMware guest) - with sv-ttk a log line painted in 36.6ms, a theme
toggle in 164ms; on plain clam the same paints cost 7.8ms/line and 31ms/toggle (4-5x). So sv-ttk is
GONE: every colour now comes from the `TOKENS` table below and is applied to the handful of ttk classes
the app actually uses. No theme package dependency, identical styling with or without extras installed.

Architecture:
  * `TOKENS[mode][role]`  - the single place a chrome colour is defined (both modes fully enumerated).
  * `apply_theme(root, mode)` - style the ttk classes + named fonts from the tokens (init + toggle).
  * `set_mode(root, mode)` - apply_theme + the Windows title bar + NOTIFY the registered components;
    components call `theme.register(self.set_theme)` once instead of app_main hand-fanning-out.
  * The oracle palettes (BUTTON_FILLS/BUTTON_FG - PL3's ButtonsLayout) and the log-level colours are
    kept verbatim; the phase bar + log pane are classic tk widgets and read them directly.
"""
from __future__ import annotations

import sys
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

# log level -> (foreground colour, bold?). FAIL (halt) is bold red; ERRR a softer red; DEBG muted.
# SUBPHASE is the SMALLER sub-phase section header (110/120/…) - phase blue, but normal weight (the
# LogView also renders it one point smaller than the bold main PHASE header); HEAD is the per-group
# column-header line (quiet grey bold - a table header, not a finding).
LOG_COLORS = {"PHASE": ("#74b9ff", True), "SUBPHASE": ("#74b9ff", False), "HEAD": ("#8f9ba2", True),
              "FAIL": ("#ff6b6b", True), "ERRR": ("#e17055", True), "WARN": ("#fdcb6e", False),
              "PASS": ("#55efc4", False), "INFO": ("#dfe6e9", False), "SKIP": ("#b2bec3", False),
              "DEBG": ("#a29bfe", False)}

# Light-mode log colours: same semantic palette but adjusted for a white background (WARN goes orange —
# yellow is invisible on white; INFO goes near-black instead of near-white).
LOG_COLORS_LIGHT = {
    "PHASE": ("#0984e3", True), "SUBPHASE": ("#0984e3", False), "HEAD": ("#7c8a91", True),
    "FAIL": ("#d63031", True), "ERRR": ("#e17055", True), "WARN": ("#e67e22", False),
    "PASS": ("#00b894", False), "INFO": ("#2d3436", False), "SKIP": ("#636e72", False),
    "DEBG": ("#6c5ce7", False),
}

DARK_BG = "#1e1e1e"
DARK_FG = "#dfe6e9"
LIGHT_BG = "#ffffff"
LIGHT_FG = "#2d3436"
APP_FONT_SIZE = 11                 # the app-wide UI font size (Monaspace Neon Var)
# The app-wide monospace font: the bundled Monaspace Neon Var family at APP_FONT_SIZE. Resolved (the
# bundled TTF registered + the family confirmed) by `apply_theme`; the default here is a safe fallback
# for any pre-theme reference. The phase bar + log viewer read this; the chrome reads the named Tk fonts.
MONO_FONT = (fonts.FALLBACK, APP_FONT_SIZE)

# The semantic chrome tokens - the ONLY place a ttk chrome colour is defined. Every role exists in both
# modes (no ad-hoc per-widget constants).
TOKENS = {
    "dark": {
        "bg": DARK_BG, "fg": DARK_FG,
        "surface": "#2b2f33",       # raised chrome: buttons, tab strip, headings
        "surface_hi": "#3a4046",    # hover/pressed
        "field": "#26292c",         # entry / tree / combo fields
        "field_alt": "#2c3034",     # the zebra stripe of the data grids
        "grid_line": "#3a3f43",     # the data-grid cell borders
        "border": "#3f4448",
        "trough": "#26292c",
        "accent": "#74b9ff",
        "disabled_fg": "#7a8288",
        "select_bg": "#264f78", "select_fg": "#ffffff",
        "phasebar_bg": DARK_BG,     # buttons pop on the window bg itself
    },
    "light": {
        "bg": LIGHT_BG, "fg": LIGHT_FG,
        "surface": "#eceff1",
        "surface_hi": "#dde3e6",
        "field": "#ffffff",
        "field_alt": "#f3f5f7",     # the zebra stripe of the data grids
        "grid_line": "#d4d9dc",     # the data-grid cell borders
        "border": "#c5cbcf",
        "trough": "#eef0f2",
        "accent": "#0984e3",
        "disabled_fg": "#95a1a6",
        "select_bg": "#cfe6ff", "select_fg": "#1e272e",
        "phasebar_bg": "#b2bec3",   # medium grey so the white/light oracle fills still stand out
    },
}

_mode = "dark"                     # the active mode (set by apply_theme; color() reads it)
_subs: list = []                   # registered component callbacks, notified by set_mode(mode)


# The NARROW chrome font for the phase-bar labels (a 2-line description must fit a fixed button width).
# Bahnschrift ships with Windows 10/11; Arial Narrow comes with Office; Segoe UI is the always-there
# last resort (not narrow, but the labels still wrap to <=2 lines at the bar's chosen width).
NARROW_CANDIDATES = ("Bahnschrift SemiCondensed", "Bahnschrift", "Arial Narrow", "Segoe UI")


def pick_narrow(families) -> str:
    """The first NARROW_CANDIDATES entry present in `families` (case-insensitive), else the last
    candidate. Pure (unit-tested); `narrow_family` adds the Tk resolution probe on top."""
    lower = {str(f).lower() for f in families}
    for cand in NARROW_CANDIDATES:
        if cand.lower() in lower:
            return cand
    return NARROW_CANDIDATES[-1]


def narrow_family(root) -> str:
    """The narrow family Tk ACTUALLY resolves (GDI can map a named instance like 'Bahnschrift
    SemiCondensed' even when families() doesn't enumerate it), falling back through the candidates."""
    try:
        for cand in NARROW_CANDIDATES:
            try:
                actual = tkfont.Font(root=root, family=cand, size=9).actual("family")
                if str(actual).lower() == cand.lower():
                    return cand
            except Exception:  # noqa: BLE001
                continue
        return pick_narrow(tkfont.families(root))
    except Exception:  # noqa: BLE001
        return NARROW_CANDIDATES[-1]


def color(role: str, mode: str | None = None) -> str:
    """The token colour for `role` in `mode` (default: the active mode)."""
    return TOKENS[mode or _mode][role]


def bg_for(mode: str) -> str:
    return TOKENS["dark" if mode == "dark" else "light"]["bg"]


def fg_for(mode: str) -> str:
    return TOKENS["dark" if mode == "dark" else "light"]["fg"]


def log_colors_for(mode: str) -> dict:
    return LOG_COLORS if mode == "dark" else LOG_COLORS_LIGHT


def phasebar_bg(mode: str) -> str:
    """The phase-bar frame background (a token role - see TOKENS)."""
    return TOKENS["dark" if mode == "dark" else "light"]["phasebar_bg"]


def register(callback) -> None:
    """Subscribe a component's `set_theme(mode)` to mode switches (call once at construction).
    `set_mode` notifies every subscriber - app_main no longer hand-fans-out."""
    if callback not in _subs:
        _subs.append(callback)


def apply_theme(root, mode: str = "dark") -> str:
    """Style the ttk classes the app uses from the TOKENS table (over the `clam` base theme), point the
    named Tk fonts at the bundled Monaspace, and remember `mode`. NEVER raises - the window must always
    come up. Returns the backend id ("native").

    Does NOT touch the Windows title bar: `darktitle.apply` calls `update_idletasks()`, which - run
    before the App has built its widgets - would flush styling against an empty window. The App applies
    the title bar separately AFTER its widgets exist; `set_mode` (the live toggle) does both."""
    global _mode
    _mode = "dark" if mode == "dark" else "light"
    c = TOKENS[_mode]
    try:
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:  # noqa: BLE001 - unknown base theme: style the current one
            pass
        root.configure(bg=c["bg"])
        style.configure(".", background=c["bg"], foreground=c["fg"], bordercolor=c["border"],
                        darkcolor=c["bg"], lightcolor=c["bg"], troughcolor=c["trough"],
                        fieldbackground=c["field"], selectbackground=c["select_bg"],
                        selectforeground=c["select_fg"], insertcolor=c["fg"], focuscolor=c["accent"],
                        arrowcolor=c["fg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TButton", background=c["surface"], foreground=c["fg"], padding=(8, 3),
                        relief="flat", shiftrelief=0)
        style.map("TButton",
                  background=[("pressed", c["surface_hi"]), ("active", c["surface_hi"])],
                  foreground=[("disabled", c["disabled_fg"])])
        style.configure("TMenubutton", background=c["surface"], foreground=c["fg"], padding=(8, 3),
                        arrowcolor=c["fg"], relief="flat")
        style.map("TMenubutton", background=[("active", c["surface_hi"])])
        # Toolbutton (the DataGrid filter/sort chips) + check/radio: clam's DEFAULT `active` state maps
        # to a LIGHT background while the root fg stays theme-white -> white-on-white hover in dark
        # mode. Pin hover to surface_hi with an explicit fg.
        style.configure("Toolbutton", background=c["surface"], foreground=c["fg"], padding=(6, 2))
        style.map("Toolbutton",
                  background=[("pressed", c["surface_hi"]), ("active", c["surface_hi"])],
                  foreground=[("disabled", c["disabled_fg"]), ("active", c["fg"])])
        for boxy in ("TCheckbutton", "TRadiobutton"):
            style.configure(boxy, background=c["bg"], foreground=c["fg"],
                            indicatorbackground=c["field"], indicatorforeground=c["fg"])
            style.map(boxy,
                      background=[("active", c["surface_hi"])],
                      foreground=[("disabled", c["disabled_fg"]), ("active", c["fg"])],
                      indicatorbackground=[("active", c["field"])])
        style.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(2, 4, 2, 0))
        style.configure("TNotebook.Tab", background=c["surface"], foreground=c["fg"],
                        padding=(12, 4), bordercolor=c["border"])
        style.map("TNotebook.Tab",
                  background=[("selected", c["bg"])],
                  foreground=[("selected", c["accent"])],
                  lightcolor=[("selected", c["bg"])],
                  expand=[("selected", (1, 1, 1, 0))])
        style.configure("Treeview", background=c["field"], fieldbackground=c["field"],
                        foreground=c["fg"], bordercolor=c["border"])
        style.map("Treeview", background=[("selected", c["select_bg"])],
                  foreground=[("selected", c["select_fg"])])
        style.configure("Treeview.Heading", background=c["surface"], foreground=c["fg"],
                        relief="flat", padding=(4, 3))
        style.map("Treeview.Heading", background=[("active", c["surface_hi"])])
        style.configure("TCombobox", fieldbackground=c["field"], background=c["surface"],
                        foreground=c["fg"], arrowcolor=c["fg"], bordercolor=c["border"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["field"])],
                  foreground=[("readonly", c["fg"])],
                  selectbackground=[("readonly", c["field"])],
                  selectforeground=[("readonly", c["fg"])])
        style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"],
                        bordercolor=c["border"], insertcolor=c["fg"])
        # NOTE deliberately NO per-orientation TScrollbar configure/map: an explicit scrollbar style
        # forces a slow clam redraw path - MEASURED at ~52ms per log-line repaint vs ~10ms without
        # (the scrollbar thumb repaints on every Text append). The scrollbars inherit every colour
        # they need from the "." root style above.
        style.configure("TProgressbar", background=c["accent"], troughcolor=c["trough"],
                        bordercolor=c["border"], lightcolor=c["accent"], darkcolor=c["accent"])
        style.configure("TSeparator", background=c["border"])
        # the Combobox popdown list is a plain tk Listbox created lazily - option_add covers new ones
        root.option_add("*TCombobox*Listbox.background", c["field"])
        root.option_add("*TCombobox*Listbox.foreground", c["fg"])
        root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
        root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])
    except Exception as exc:  # noqa: BLE001
        print(f"[theme] styling failed ({exc}) - launching unstyled", file=sys.stderr)
    _apply_app_font(root)
    return "native"


def set_mode(root, mode: str) -> str:
    """The LIVE mode switch: restyle from the tokens, flip the Windows title bar, then notify every
    registered component (`register`). Returns the backend id."""
    backend = apply_theme(root, mode)
    try:
        from pipeline4.gui import darktitle
        darktitle.apply(root, _mode == "dark")
    except Exception:  # noqa: BLE001
        pass
    for callback in list(_subs):
        try:
            callback(_mode)
        except Exception as exc:  # noqa: BLE001 - one broken subscriber must not stop the switch
            print(f"[theme] subscriber {callback!r} failed: {exc}", file=sys.stderr)
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
