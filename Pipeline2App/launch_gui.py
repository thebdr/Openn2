#!/usr/bin/env python3
"""Launch the Pipeline2 main GUI (full pipeline)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make `pipeline2` importable
from pipeline2.gui import gui

if __name__ == "__main__":
    gui.main()
