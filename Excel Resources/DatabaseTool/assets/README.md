# assets

App icon for the Pipeline2 GUI (`gui.py`).

- `Pipeline2.ico` (preferred) or `Pipeline2.png` — the window/taskbar icon.
  `gui.py` loads `.ico` via `iconbitmap`, else `.png` via `iconphoto`; if neither
  is present the GUI still runs (just no custom icon). A PNG is fine on Tk 8.6;
  a multi-resolution `.ico` gives a crisper taskbar icon.
