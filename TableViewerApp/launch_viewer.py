"""Launch the standalone Table Viewer: `python launch_viewer.py [path\\to\\table.csv|.xlsx]`."""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tableviewer.app import ViewerApp  # noqa: E402


def main() -> None:
    root = tk.Tk()
    ViewerApp(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == "__main__":
    main()
