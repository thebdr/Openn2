"""Sycon5App entry point - the users' GUI (mirrors Pipeline5App/launch_gui.py).
Usage:  launch_gui.py [<PRODUCTION folder>]  - double-click it, or run it with any Python: it re-launches itself with
the repo venv (`..\\.venv\\Scripts\\python.exe`, where pywinauto and the steps' packages live) when started with
another one (user 2026-10-25: "launch_gui.py opens nothing" - the system Python had no pywinauto and the console
closed on the traceback). A startup error is shown in a message box, never lost with a closing console.
Launched with python.exe (a console) the Stop button can ask a running build to close SYCON.net; with pythonw.exe it
can only terminate the build (sycon5.gui.Runner.stop)."""
import os
import subprocess
import sys

APP = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(os.path.dirname(APP), ".venv", "Scripts", "python.exe")


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def main():
    if os.path.exists(VENV_PYTHON) and not same_file(sys.executable, VENV_PYTHON) and not os.environ.get("SYCON5_NO_REEXEC"):
        return subprocess.call([VENV_PYTHON, os.path.abspath(__file__)] + sys.argv[1:], cwd=APP)
    sys.path.insert(0, APP)
    try:
        from sycon5.gui import main as gui_main
        return gui_main()
    except Exception:  # noqa: BLE001 - whatever stops the window from opening is shown, not lost
        import ctypes
        import traceback
        text = traceback.format_exc()
        print(text, file=sys.stderr)
        ctypes.windll.user32.MessageBoxW(0, "The GUI could not start (%s):\n\n%s" % (sys.executable, text), "Sycon5App", 0x10)
        return 1


if __name__ == "__main__":
    sys.exit(main())
