"""Dark Windows title bar (the Pipeline2 GUI's title bar stayed white - plan §4 GUI architecture).

Sets the DWM `DWMWA_USE_IMMERSIVE_DARK_MODE` attribute on a Tk toplevel's native HWND so the OS
draws the caption/title bar dark. No-op off Windows or when the call fails (the window just keeps the
default light bar). Call after the window exists and is mapped.
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
        # a Tk toplevel's winfo_id() is the child frame; the decorated caption lives on its parent
        # (WS_CAPTION). Target whichever HWND actually carries the caption.
        child = window.winfo_id()
        parent = ctypes.windll.user32.GetParent(child)
        GWL_STYLE, WS_CAPTION = -16, 0x00C00000

        def _has_caption(h):
            return bool(h) and bool(ctypes.windll.user32.GetWindowLongW(h, GWL_STYLE) & WS_CAPTION)

        hwnd = child if _has_caption(child) else (parent if _has_caption(parent) else (parent or child))
        value = ctypes.c_int(1 if dark else 0)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20          # Win10 2004+ ; 19 on older 1809/1903 builds
        for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, 19):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), ctypes.c_uint(attr),
                ctypes.byref(value), ctypes.sizeof(value))
            if res == 0:
                # SWP_NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED -> repaint the caption immediately
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
                return True
    except Exception:  # noqa: BLE001
        pass
    return False
