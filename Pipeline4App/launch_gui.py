"""Launch the PL4 operator GUI:  python launch_gui.py

Adds Pipeline4App to sys.path so `import pipeline4...` resolves when run from anywhere.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline4.gui.app_main import main  # noqa: E402  (after the path insert)

if __name__ == "__main__":
    main()
