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


def log_tags(dark: bool) -> dict:
    """level -> Text tag config (foreground + optional font)."""
    if dark:
        return {
            "ERROR": {"foreground": "#ff6b6b", "font": ("Consolas", 10, "bold")},
            "FAIL": {"foreground": "#ff6b6b", "font": ("Consolas", 10, "bold")},
            "WARNING": {"foreground": "#e0a458"},
            "PASS": {"foreground": "#3fb950"},
            "OK": {"foreground": "#3fb950", "font": ("Consolas", 10, "bold")},
            "INFO": {"foreground": "#a8a8a8"},
            "SECTION": {"foreground": "#4ea1ff", "font": ("Consolas", 11, "bold")},
        }
    return {
        "ERROR": {"foreground": "#c0282d", "font": ("Consolas", 10, "bold")},
        "FAIL": {"foreground": "#c0282d", "font": ("Consolas", 10, "bold")},
        "WARNING": {"foreground": "#b35c00"},
        "PASS": {"foreground": "#1a7f37"},
        "OK": {"foreground": "#1a7f37", "font": ("Consolas", 10, "bold")},
        "INFO": {"foreground": "#555555"},
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
