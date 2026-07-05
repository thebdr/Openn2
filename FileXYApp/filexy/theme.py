"""The viewer's LOOK, as rebindable module state - so the standalone app has a complete dark/light
palette out of the box, and an EMBEDDER (Pipeline4) can point the whole package at its own tokens
and fonts with three assignments:

    filexy.theme.TOKENS = my_tokens          # same role names
    filexy.theme.mono_family = my_resolver   # (widget) -> family name
    filexy.theme.narrow_family = my_resolver

The grid reads these at call time (module-attribute lookup), so rebinding before widget
construction is all an embedder needs."""
from __future__ import annotations

import sys
import tkinter.font as tkfont
from tkinter import ttk

# The role names the grid + popups read. An embedder's TOKENS must carry the same keys.
TOKENS = {
    "dark": {
        "bg": "#1e1e1e", "fg": "#dfe6e9",
        "surface": "#2b2f33", "surface_hi": "#3a4046",
        "field": "#26292c", "field_alt": "#2c3034",
        "grid_line": "#3a3f43", "border": "#3f4448", "trough": "#26292c",
        "accent": "#74b9ff", "disabled_fg": "#7a8288",
        "select_bg": "#264f78", "select_fg": "#ffffff",
    },
    "light": {
        "bg": "#ffffff", "fg": "#2d3436",
        "surface": "#eceff1", "surface_hi": "#dde3e6",
        "field": "#ffffff", "field_alt": "#f3f5f7",
        "grid_line": "#d4d9dc", "border": "#c5cbcf", "trough": "#eef0f2",
        "accent": "#0984e3", "disabled_fg": "#95a1a6",
        "select_bg": "#cfe6ff", "select_fg": "#1e272e",
    },
}

MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
NARROW_CANDIDATES = ("Bahnschrift SemiCondensed", "Bahnschrift", "Arial Narrow", "Segoe UI")


def _pick(candidates, families) -> str:
    lowered = {f.lower(): f for f in families}
    for name in candidates:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return candidates[-1]


def mono_family(widget) -> str:
    """The grid's monospace family: the first installed MONO_CANDIDATES entry."""
    return _pick(MONO_CANDIDATES, tkfont.families(widget))


def narrow_family(widget) -> str:
    """The condensed family long cells render in: the first installed NARROW_CANDIDATES entry."""
    return _pick(NARROW_CANDIDATES, tkfont.families(widget))


def apply(root, mode: str = "dark") -> None:
    """Minimal STANDALONE-app styling from the tokens (clam base): window/frame/label/button/entry
    colours + the hover states clam gets wrong on dark (Toolbutton/check boxes go light-on-light).
    An embedder never calls this - it themes its own app and just rebinds TOKENS."""
    c = TOKENS["dark" if mode == "dark" else "light"]
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
                        selectforeground=c["select_fg"], insertcolor=c["fg"], arrowcolor=c["fg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TButton", background=c["surface"], foreground=c["fg"], padding=(8, 3))
        style.map("TButton", background=[("pressed", c["surface_hi"]), ("active", c["surface_hi"])])
        style.configure("Toolbutton", background=c["surface"], foreground=c["fg"], padding=(6, 2))
        style.map("Toolbutton",
                  background=[("pressed", c["surface_hi"]), ("active", c["surface_hi"])],
                  foreground=[("active", c["fg"])])
        style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"],
                        indicatorbackground=c["field"], indicatorforeground=c["fg"])
        style.map("TCheckbutton", background=[("active", c["surface_hi"])],
                  foreground=[("active", c["fg"])])
        style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"],
                        insertcolor=c["fg"])
        style.configure("TCombobox", fieldbackground=c["field"], background=c["surface"],
                        foreground=c["fg"], arrowcolor=c["fg"])
        style.map("TCombobox", fieldbackground=[("readonly", c["field"])],
                  foreground=[("readonly", c["fg"])])
    except Exception as exc:  # noqa: BLE001
        print(f"[filexy] styling failed ({exc}) - running unstyled", file=sys.stderr)
