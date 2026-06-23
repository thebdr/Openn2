"""Thin launcher for the Pipeline3 operator GUI (the "Broski Session" - the main profile).

Puts Pipeline3App on sys.path and starts the main window. Run with `pythonw launch_gui.py` for no
console window, or `python launch_gui.py` while developing.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline3.gui import app_main

if __name__ == "__main__":
    app_main.main()
