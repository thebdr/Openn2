"""Sycon5App entry point - the users' GUI (mirrors Pipeline5App/launch_gui.py).
Usage (the repo venv):  C:\\Source\\Repos\\_Openn5\\.venv\\Scripts\\python.exe launch_gui.py [<PRODUCTION folder>]
Launched with python.exe (a console) the Stop button can ask a running build to close SYCON.net; with pythonw.exe
it can only terminate the build (sycon5.gui.Runner.stop)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from sycon5.gui import main
    sys.exit(main())
