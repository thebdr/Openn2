"""extedit.py - open a file in an EXTERNAL editor that handles it natively.

For spreadsheets (.xlsx/.xlsm) this preserves the formulas / array suggested-type / VBA the pipeline
relies on - which an in-app openpyxl save would drop. Prefers **LibreOffice** (FOSS; keeps formulas +
cached values, warns on unsupported), then Excel / the OS default handler. Best-effort, never raises.
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


def open_external(path: str, prefer: str = "auto") -> tuple[bool, str]:
    """Open `path` in an external editor. `prefer`: 'auto' (LibreOffice if present, else default),
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
    except Exception:  # noqa: BLE001
        return _default(path)


def reveal(path: str) -> tuple[bool, str]:
    """Open the file's containing folder in the OS file manager with the file SELECTED
    (Windows `explorer /select`, macOS `open -R`, else `xdg-open <dir>`). Returns (ok, message)."""
    if not path or not os.path.exists(path):
        return False, f"not found: {path}"
    try:
        if sys.platform == "win32":
            # explorer returns exit 1 even on success - fire and forget (don't wait/check)
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            return True, f"revealed {os.path.basename(path)} in Explorer"
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
            return True, f"revealed {os.path.basename(path)}"
        subprocess.Popen(["xdg-open", os.path.dirname(os.path.abspath(path))])
        return True, f"opened {os.path.dirname(path)}"
    except Exception:  # noqa: BLE001
        return _default(os.path.dirname(os.path.abspath(path)))


def _default(path: str) -> tuple[bool, str]:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True, f"opened: {os.path.basename(path)}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
