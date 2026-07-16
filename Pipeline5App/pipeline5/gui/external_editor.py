"""Open a file / its folder in an external application - clean-room port of PL3's `gui/extedit.py`.

`open_external(path)` launches the file in LibreOffice when it's installed (a spreadsheet opens in Calc),
else the OS default app; `reveal(path)` opens the containing folder with the file selected. Both return
`(ok, message)` so the GUI can show the outcome in the status bar. No temp files, no round-trip - the
external app owns the file from there (the Files tab is view-only; editing happens out-of-app).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

_LO_PATHS = [r"C:\Program Files\LibreOffice\program\soffice.exe",
             r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"]
_SPREADSHEET = (".xlsx", ".xlsm", ".xls", ".csv")


def libreoffice() -> str | None:
    """The LibreOffice launcher path if installed, else None."""
    return (shutil.which("soffice") or shutil.which("scalc")
            or next((p for p in _LO_PATHS if os.path.exists(p)), None))


def open_external(path: str, prefer: str = "auto") -> tuple:
    """Open `path` in an external editor. `prefer`: 'auto' (LibreOffice if present, else the OS default),
    'libreoffice', or 'default'. Returns (ok, message)."""
    if not path or not os.path.exists(path):
        return False, f"not found: {path}"
    lo = libreoffice()
    try:
        if lo and prefer in ("auto", "libreoffice"):
            args = [lo, "--calc", path] if path.lower().endswith(_SPREADSHEET) else [lo, path]
            subprocess.Popen(args, close_fds=True)
            return True, f"opened in LibreOffice: {os.path.basename(path)}"
        if prefer == "libreoffice" and not lo:
            return False, "LibreOffice not found (install it, or use the OS default)"
        return _default(path)
    except Exception:  # noqa: BLE001  - any launch failure falls back to the OS default
        return _default(path)


def reveal(path: str) -> tuple:
    """Open the file's containing folder in the OS file manager with the file SELECTED (Windows
    `explorer /select`, macOS `open -R`, else `xdg-open <dir>`). Returns (ok, message)."""
    if not path or not os.path.exists(path):
        return False, f"not found: {path}"
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            return True, f"revealed {os.path.basename(path)} in Explorer"
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
            return True, f"revealed {os.path.basename(path)}"
        subprocess.Popen(["xdg-open", os.path.dirname(os.path.abspath(path))])
        return True, f"opened {os.path.dirname(path)}"
    except Exception:  # noqa: BLE001
        return _default(os.path.dirname(os.path.abspath(path)))


def _default(path: str) -> tuple:
    """Open `path` with the OS default handler (`os.startfile` / `open` / `xdg-open`)."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606  - opening a project file in its default app is the intent
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True, f"opened: {os.path.basename(path)}"
    except Exception as error:  # noqa: BLE001
        return False, str(error)
