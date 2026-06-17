#!/usr/bin/env python3
"""Launch the slim I/O List Checker (designer) GUI - validation only."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # make `pipeline2` importable
from pipeline2.gui import gui_designer

if __name__ == "__main__":
    gui_designer.main()
