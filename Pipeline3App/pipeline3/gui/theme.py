"""theme.py - the Sun Valley (sv-ttk) dark/light theme + the semantic phase-bar button colours.

`apply_base` applies **sv-ttk** (modern Win11-style ttk theme) and sets the bundled **Monaspace Neon**
as the default UI font, returning a palette read back from the active theme (so the classic-tk widgets
- the log Text, the dropdown canvas - match). sv-ttk's buttons are image-based and ignore a custom
`background`, so the phase-bar buttons are classic `tk.Button`s coloured from `tk_button_opts` with the
`assets/ButtonsLayout.xlsx` fills (pink run / white phase / grey chevron / white action / light-blue
open / orange special / grey disabled). Falls back to a hand-rolled `clam` dark theme if sv-ttk is
absent. Dark is the default; the window title bar is darkened separately (`darktitle.apply`).
"""
from __future__ import annotations
import tkinter.font as tkfont
from tkinter import ttk

GLYPH_FONT = "Segoe UI Symbol"        # for the ▼ chevron glyph (a mono face may lack it)
EMOJI_FONT = "Segoe UI Emoji"         # for the ➡/⬇ flow arrows - renders them BOLD (even monochrome on Tk 8.6)

LIGHT = {"name": "light", "bg": "#fafafa", "fg": "#1c1c1c", "field": "#ffffff", "border": "#c8c8c8",
         "log_bg": "#ffffff", "log_fg": "#1c1c1c", "accent": "#0b5fff", "select": "#cce4ff"}
DARK = {"name": "dark", "bg": "#1c1c1c", "fg": "#fafafa", "field": "#2b2b2b", "border": "#3a3a3a",
        "log_bg": "#1c1c1c", "log_fg": "#e6e6e6", "accent": "#4ea1ff", "select": "#2f5d8a"}


def palette(dark: bool = True) -> dict:
    return DARK if dark else LIGHT


# Semantic phase-bar button fills (matching assets/ButtonsLayout.xlsx). {style: {bg, fg, active}}.
_BUTTON_LIGHT = {
    "Run":      {"bg": "#f2cfee", "fg": "#1c1c1c", "active": "#e7b6e1"},  # pink  (run-all)
    "Phase":    {"bg": "#ffffff", "fg": "#1c1c1c", "active": "#eef2f7"},  # white (phase header)
    "Chevron":  {"bg": "#d9d9d9", "fg": "#1c1c1c", "active": "#c8c8c8"},  # grey  (open popup)
    "Action":   {"bg": "#ffffff", "fg": "#1c1c1c", "active": "#eef2f7"},  # white (generate/run step)
    "Open":     {"bg": "#cfe2f3", "fg": "#10243a", "active": "#bcd6ee"},  # light blue (open file/folder)
    "Special":  {"bg": "#fce5cd", "fg": "#5a3b16", "active": "#f8d6b0"},  # light orange (special)
    "Disabled": {"bg": "#ececec", "fg": "#9a9a9a", "active": "#ececec"},  # greyed stub
}
_BUTTON_DARK = {
    "Run":      {"bg": "#6d4869", "fg": "#f7e8f4", "active": "#825a7d"},
    "Phase":    {"bg": "#2f2f2f", "fg": "#f0f0f0", "active": "#3c3c3c"},
    "Chevron":  {"bg": "#3a3a3a", "fg": "#e6e6e6", "active": "#4a4a4a"},
    "Action":   {"bg": "#2f2f2f", "fg": "#f0f0f0", "active": "#3c3c3c"},
    "Open":     {"bg": "#27384a", "fg": "#cfe2f3", "active": "#34506b"},
    "Special":  {"bg": "#4d3a23", "fg": "#fce5cd", "active": "#62492c"},
    "Disabled": {"bg": "#262626", "fg": "#6a6a6a", "active": "#262626"},
}


def button_styles(dark: bool) -> dict:
    return _BUTTON_DARK if dark else _BUTTON_LIGHT


def tk_button_opts(kind: str, dark: bool, font_family: str, *, bold: bool = False) -> dict:
    """Classic-`tk.Button` kwargs for a phase-bar button of semantic `kind`
    (run/phase/chevron/action/open/special/disabled). Honors the exact ButtonsLayout colour
    (sv-ttk's themed buttons can't)."""
    styles = button_styles(dark)
    c = styles.get(kind.capitalize(), styles["Action"])
    font = (GLYPH_FONT, 11) if kind == "chevron" else (font_family, 9, "bold") if bold else (font_family, 9)
    return dict(background=c["bg"], foreground=c["fg"], activebackground=c["active"],
                activeforeground=c["fg"], disabledforeground=styles["Disabled"]["fg"],
                relief="raised", borderwidth=1, highlightthickness=0, font=font,
                cursor="hand2" if kind not in ("disabled",) else "arrow")


def log_tags(dark: bool, font_family: str) -> dict:
    """level -> Text tag config (foreground + optional bold font)."""
    bold = (font_family, 10, "bold")
    if dark:
        return {"ERROR": {"foreground": "#ff6b6b", "font": bold}, "FAIL": {"foreground": "#ff6b6b", "font": bold},
                "HALT": {"foreground": "#ff6b6b", "font": bold}, "WARNING": {"foreground": "#e0a458"},
                "PASS": {"foreground": "#9ad67d"}, "SKIP": {"foreground": "#a8a8a8"},
                "OK": {"foreground": "#3fb950", "font": bold}, "INFO": {"foreground": "#e6e6e6"},
                "SECTION": {"foreground": "#4ea1ff", "font": (font_family, 11, "bold")}}
    return {"ERROR": {"foreground": "#c0282d", "font": bold}, "FAIL": {"foreground": "#c0282d", "font": bold},
            "HALT": {"foreground": "#c0282d", "font": bold}, "WARNING": {"foreground": "#b35c00"},
            "PASS": {"foreground": "#1a7f37"}, "SKIP": {"foreground": "#777777"},
            "OK": {"foreground": "#1a7f37", "font": bold}, "INFO": {"foreground": "#1c1c1c"},
            "SECTION": {"foreground": "#003a8c", "font": (font_family, 11, "bold")}}


def _apply_clam(style, pal: dict) -> None:
    """Fallback theme when sv-ttk is unavailable (the previous hand-rolled dark clam)."""
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    bg, fg, field = pal["bg"], pal["fg"], pal["field"]
    style.configure(".", background=bg, foreground=fg, fieldbackground=field, bordercolor=pal["border"],
                    lightcolor=bg, darkcolor=bg, troughcolor=pal["field"], arrowcolor=fg, insertcolor=fg)
    for w in ("TFrame", "TLabel", "TCheckbutton", "TSeparator", "TPanedwindow"):
        style.configure(w, background=bg, foreground=fg)
    style.configure("TButton", background=pal["field"], foreground=fg)
    style.configure("TProgressbar", background=pal["accent"], troughcolor=pal["field"])


def apply_base(root, font_family: str, dark: bool = True) -> dict:
    """Apply sv-ttk (or the clam fallback) + set the Monaspace default font. Returns a palette whose
    bg/fg are read back from the active theme so classic-tk widgets match."""
    style = ttk.Style(root)
    pal = dict(DARK if dark else LIGHT)
    try:
        import sv_ttk
        sv_ttk.set_theme("dark" if dark else "light")
        pal["sv"] = True
    except Exception:  # noqa: BLE001
        _apply_clam(style, pal)
        pal["sv"] = False
    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont"):
        try:
            tkfont.nametofont(fname).configure(family=font_family, size=10)
        except Exception:  # noqa: BLE001
            pass
    pal["bg"] = style.lookup("TFrame", "background") or pal["bg"]
    pal["fg"] = style.lookup("TLabel", "foreground") or pal["fg"]
    pal["log_bg"] = pal["bg"]
    pal["log_fg"] = pal["fg"]
    return pal
