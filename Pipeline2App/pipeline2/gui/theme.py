"""theme.py - light/dark palettes and ttk theming for the Pipeline2 GUI.

Shared by gui.py (window chrome, log) and editor.py (Files tab, tksheet grid).
"""
from __future__ import annotations

TAB_FONT = ("Consolas", 16)                    # notebook tab labels
TABLE_FONT = ("Consolas", 12, "normal")        # tksheet cells
TABLE_HEADER_FONT = ("Consolas", 12, "bold")   # tksheet headers/index

# Table viewer colours (same in both modes, by request): a steel-blue header with
# white text, then zebra body rows - odd rows light blue, even rows light grey.
HEADER = {"bg": "#4682b4", "fg": "#ffffff"}     # steel blue / white (column header)
ZEBRA_ODD = {"bg": "#cfe2f3", "fg": "#10243a"}  # light blue
ZEBRA_EVEN = {"bg": "#ededed", "fg": "#1c1c1c"}  # light grey

LIGHT = {
    "name": "light",
    "bg": "#f0f0f0", "fg": "#1c1c1c", "field": "#ffffff", "border": "#c8c8c8",
    "btn": "#e6e6e6", "btn_active": "#d4d4d4",
    "tab": "#e1e1e1", "tab_sel": "#ffffff",
    "select": "#cce4ff", "accent": "#0b5fff",
    "log_bg": "#fbfbfb", "log_fg": "#1c1c1c",
    "sheet_theme": "light blue",
}
DARK = {
    "name": "dark",
    "bg": "#252526", "fg": "#e6e6e6", "field": "#2d2d30", "border": "#3c3c3c",
    "btn": "#3a3a3d", "btn_active": "#4a4a4d",
    "tab": "#2d2d30", "tab_sel": "#1e1e1e",
    "select": "#094771", "accent": "#4ea1ff",
    "log_bg": "#1e1e1e", "log_fg": "#e6e6e6",
    "sheet_theme": "dark blue",
}


def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT


# Semantic phase-bar button fills (matching assets/ButtonsLayout.xlsx). Light mode reproduces the
# spreadsheet's pastel fills with dark text; dark mode uses muted/darker tints with light text.
# {style_name: {bg, fg, active}} - active is the hover/pressed shade.
_BUTTON_LIGHT = {
    "Run.TButton":      {"bg": "#f2cfee", "fg": "#1c1c1c", "active": "#e7b6e1"},  # pink  (run-all)
    "Phase.TButton":    {"bg": "#ffffff", "fg": "#1c1c1c", "active": "#eef2f7"},  # white (phase header)
    "Chevron.TButton":  {"bg": "#d9d9d9", "fg": "#1c1c1c", "active": "#c8c8c8"},  # grey  (open popup)
    "Action.TButton":   {"bg": "#ffffff", "fg": "#1c1c1c", "active": "#eef2f7"},  # white (generate/run step)
    "Open.TButton":     {"bg": "#cfe2f3", "fg": "#10243a", "active": "#bcd6ee"},  # light blue (open file/folder)
    "Special.TButton":  {"bg": "#fce5cd", "fg": "#5a3b16", "active": "#f8d6b0"},  # light orange (special)
    "Disabled.TButton": {"bg": "#f0f0f0", "fg": "#9a9a9a", "active": "#f0f0f0"},  # greyed stub
}
_BUTTON_DARK = {
    "Run.TButton":      {"bg": "#5a3a57", "fg": "#f3e0f0", "active": "#6d4869"},
    "Phase.TButton":    {"bg": "#2d2d30", "fg": "#e6e6e6", "active": "#3a3a3d"},
    "Chevron.TButton":  {"bg": "#3a3a3d", "fg": "#e6e6e6", "active": "#4a4a4d"},
    "Action.TButton":   {"bg": "#2d2d30", "fg": "#e6e6e6", "active": "#3a3a3d"},
    "Open.TButton":     {"bg": "#27384a", "fg": "#cfe2f3", "active": "#324a61"},
    "Special.TButton":  {"bg": "#4d3a23", "fg": "#fce5cd", "active": "#5f4830"},
    "Disabled.TButton": {"bg": "#2a2a2c", "fg": "#6a6a6a", "active": "#2a2a2c"},
}


def button_styles(dark: bool) -> dict:
    """The semantic phase-bar button styles for the current palette."""
    return _BUTTON_DARK if dark else _BUTTON_LIGHT


def log_tags(dark: bool) -> dict:
    """level -> Text tag config (foreground + optional font)."""
    if dark:
        return {
            "ERROR": {"foreground": "#ff6b6b", "font": ("Consolas", 10, "bold")},
            "FAIL": {"foreground": "#ff6b6b", "font": ("Consolas", 10, "bold")},
            "WARNING": {"foreground": "#e0a458"},
            "PASS": {"foreground": "#D7FFAF"},
            "SKIP": {"foreground": "#a8a8a8"},
            "OK": {"foreground": "#3fb950", "font": ("Consolas", 10, "bold")},
            "INFO": {"foreground": "#FFE697"},
            "SECTION": {"foreground": "#4ea1ff", "font": ("Consolas", 11, "bold")},
        }
    return {
        "ERROR": {"foreground": "#c0282d", "font": ("Consolas", 10, "bold")},
        "FAIL": {"foreground": "#c0282d", "font": ("Consolas", 10, "bold")},
        "WARNING": {"foreground": "#b35c00"},
        "PASS": {"foreground": "#1a7f37"},
        "SKIP": {"foreground": "#777777"},
        "OK": {"foreground": "#1a7f37", "font": ("Consolas", 10, "bold")},
        "INFO": {"foreground": "#8a6d00"},
        "SECTION": {"foreground": "#003a8c", "font": ("Consolas", 11, "bold")},
    }


def apply_ttk(style, pal: dict) -> None:
    """Recolour the ttk widgets via the (fully configurable) 'clam' theme, and set
    the notebook tab font to Consolas 16."""
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    bg, fg, field = pal["bg"], pal["fg"], pal["field"]
    style.configure(".", background=bg, foreground=fg, fieldbackground=field,
                    bordercolor=pal["border"], lightcolor=bg, darkcolor=bg,
                    troughcolor=pal["tab"], arrowcolor=fg, insertcolor=fg)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TButton", background=pal["btn"], foreground=fg)
    style.map("TButton", background=[("active", pal["btn_active"]), ("pressed", pal["btn_active"])])
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.map("TCheckbutton", background=[("active", bg)])
    style.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg)
    style.configure("TCombobox", fieldbackground=field, foreground=fg, background=pal["btn"], arrowcolor=fg)
    style.configure("TNotebook", background=bg, bordercolor=pal["border"])
    style.configure("TNotebook.Tab", font=TAB_FONT, padding=(14, 5),
                    background=pal["tab"], foreground=fg)
    style.map("TNotebook.Tab",
              background=[("selected", pal["tab_sel"])],
              foreground=[("selected", fg)])
    style.configure("Treeview", background=field, fieldbackground=field, foreground=fg)
    style.map("Treeview", background=[("selected", pal["select"])], foreground=[("selected", fg)])
    style.configure("Treeview.Heading", background=pal["tab"], foreground=fg)
    style.configure("TPanedwindow", background=bg)
    style.configure("TProgressbar", background=pal["accent"], troughcolor=pal["tab"])
    style.configure("TScrollbar", background=pal["tab"], troughcolor=bg, arrowcolor=fg)

    # the semantic phase-bar buttons (assets/ButtonsLayout.xlsx colours)
    styles = button_styles(pal["name"] == "dark")
    bold = {"Run.TButton", "Phase.TButton"}
    muted_fg = styles["Disabled.TButton"]["fg"]
    for name, c in styles.items():
        pad = (6, 3)
        if name == "Chevron.TButton":
            font = ("Segoe UI", 10)                    # keep the ▼ glyph in a font that renders it
            pad = (6, 0)                               # minimal vertical padding -> a short chevron strip
        elif name in bold:
            font = ("Courier New", 9, "bold")
        else:
            font = ("Courier New", 9)
        # anchor + justify center: labels (incl. wrapped multi-line ones) are centred horizontally
        style.configure(name, background=c["bg"], foreground=c["fg"], padding=pad,
                        anchor="center", justify="center",
                        bordercolor=pal["border"], focuscolor=c["bg"], relief="raised", font=font)
        style.map(name,
                  background=[("disabled", c["bg"]), ("active", c["active"]), ("pressed", c["active"])],
                  foreground=[("disabled", muted_fg)])
