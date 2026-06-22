"""Bundled-font loading for the GUI.

Registers `assets/fonts/MonaspaceNeon-Var.ttf` privately for this process (Windows GDI
`AddFontResourceExW(FR_PRIVATE)`) so the GUI uses **Monaspace Neon** even where it is not installed
system-wide (and inside the packaged exe). `family(root)` returns the Tk family string that actually
resolves to a Monaspace face, else a monospace fallback. Monaspace Neon Var is a *variable* font and
Tk 8.6 has no variable-axis support, so it renders at the file's default instance.
"""
from __future__ import annotations
import os
import sys

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT_PATH = os.path.join(APP_ROOT, "assets", "fonts", "MonaspaceNeon-Var.ttf")
FAMILY = "Monaspace Neon Var"      # the Tk family the registered face resolves to (verified on Tk 8.6)
FALLBACK = "Consolas"

_registered = False


def register() -> bool:
    """`AddFontResourceEx(FR_PRIVATE)` the bundled TTF for this process. Idempotent, Windows-only,
    safe to call before `tk.Tk()`. Returns False (no-op) off Windows or when the file is missing."""
    global _registered
    if _registered:
        return True
    if sys.platform != "win32" or not os.path.exists(FONT_PATH):
        return False
    try:
        import ctypes
        FR_PRIVATE = 0x10
        added = ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(FONT_PATH), FR_PRIVATE, 0)
        _registered = bool(added)
        return _registered
    except Exception:  # noqa: BLE001
        return False


def family(root) -> str:
    """The font family to use: FAMILY when Tk resolves it to a real Monaspace face, else FALLBACK."""
    import tkinter.font as tkfont
    try:
        if "monaspace" in tkfont.Font(root=root, family=FAMILY, size=12).actual("family").lower():
            return FAMILY
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK
