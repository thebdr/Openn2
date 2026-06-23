"""excel.py - open a workbook in Excel at a Sheet!Cell via COM (pywin32), for the log's clickable
links. Reuses an already-open Excel instance when present; falls back to `os.startfile` (no cell
navigation) when COM/Excel is unavailable or off Windows. Best-effort - never raises.
"""
from __future__ import annotations
import os
import sys


def goto(path: str, sheet: str, cell: str) -> tuple[bool, str]:
    """Open `path` and select `sheet`!`cell` in Excel. Returns (ok, message)."""
    if not path or not os.path.exists(path):
        return False, f"not found: {path}"
    if sys.platform != "win32":
        return _startfile(path)
    try:
        import pythoncom  # noqa: F401  (initializes COM on this worker thread)
        import win32com.client as win32
        pythoncom.CoInitialize()
        try:
            xl = win32.GetActiveObject("Excel.Application")
        except Exception:  # noqa: BLE001
            xl = win32.DispatchEx("Excel.Application")
        xl.Visible = True
        target = os.path.normcase(os.path.abspath(path))
        wb = None
        for w in list(xl.Workbooks):
            try:
                if os.path.normcase(w.FullName) == target:
                    wb = w
                    break
            except Exception:  # noqa: BLE001
                pass
        if wb is None:
            wb = xl.Workbooks.Open(os.path.abspath(path))
        try:
            ws = wb.Worksheets(sheet)
            ws.Activate()
            xl.Goto(ws.Range(cell), True)
            _bring_to_front(xl)
            return True, f"opened {sheet}!{cell}"
        except Exception:  # noqa: BLE001
            wb.Activate()
            _bring_to_front(xl)
            return True, f"opened {os.path.basename(path)} (sheet/cell not located)"
    except Exception:  # noqa: BLE001
        return _startfile(path)


def _bring_to_front(xl) -> None:
    """Force the Excel window to the foreground (works around Windows' focus-steal lock) so a clicked
    log link actually surfaces Excel at the cell, not behind the GUI. Best-effort - never raises.
    Ported from Pipeline2's `_bring_to_front`: restore if minimized, then AttachThreadInput around
    BringWindowToTop + SetForegroundWindow."""
    try:
        hwnd = int(xl.Hwnd)
    except Exception:  # noqa: BLE001
        return
    if not hwnd:
        return
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        fg = win32gui.GetForegroundWindow()
        cur = win32api.GetCurrentThreadId()
        other = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        attached = bool(other) and other != cur
        if attached:
            win32process.AttachThreadInput(other, cur, True)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached:
                win32process.AttachThreadInput(other, cur, False)
    except Exception:  # noqa: BLE001
        try:
            xl.ActiveWindow.Activate()
        except Exception:  # noqa: BLE001
            pass


def _startfile(path: str) -> tuple[bool, str]:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return True, f"opened {os.path.basename(path)}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
