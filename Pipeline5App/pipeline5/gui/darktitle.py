"""Windows immersive dark title bar helper — port of PL3's gui/darktitle.py.

`apply(window, dark)` sets (or unsets) DWMWA_USE_IMMERSIVE_DARK_MODE on the Win32 caption window
then forces an immediate repaint via SetWindowPos(SWP_FRAMECHANGED). Silently no-ops on non-Windows
or when the DWM APIs are unavailable.
"""
from __future__ import annotations

import sys


def apply(window, dark: bool = True) -> bool:
    """Set `window`'s native title bar to dark (or back to light when `dark=False`). Returns True on
    success."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        window.update_idletasks()
        # winfo_id() is the Tk client child frame; the decorated caption lives on whichever window
        # carries WS_CAPTION — typically the parent Win32 frame.
        child = window.winfo_id()
        parent = ctypes.windll.user32.GetParent(child)
        GWL_STYLE, WS_CAPTION = -16, 0x00C00000

        def _has_caption(h):
            return bool(h) and bool(ctypes.windll.user32.GetWindowLongW(h, GWL_STYLE) & WS_CAPTION)

        hwnd = child if _has_caption(child) else (parent if _has_caption(parent) else (parent or child))
        value = ctypes.c_int(1 if dark else 0)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20          # Win10 20H1+ / Win11; 19 on older 1809/1903
        for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, 19):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), ctypes.c_uint(attr),
                ctypes.byref(value), ctypes.sizeof(value))
            if res == 0:
                # SWP_NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED — force immediate non-client area repaint
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
                return True
    except Exception:  # noqa: BLE001
        pass
    return False
