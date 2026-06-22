"""widgets.py - small shared GUI building blocks.

`editor_header` is the common header every Files-tab editor (CSV grid / text / xlsx preview / the
YAML-JSON-XML object editor) puts on top: a **selectable read-only field with the file's complete
absolute path** (copyable, scrolls for long paths) and a button bar pre-seeded with an **Open folder**
button (reveals the file in the OS file manager). The caller packs its own buttons (Save/Reload/…)
into the returned bar.
"""
from __future__ import annotations
import os
from tkinter import ttk

from pipeline3.gui import extedit


def editor_header(parent, path, on_status=lambda *_a: None):
    """(frame, button_bar): a full-path strip + a button bar (with Open-folder). Pack `frame` at the
    top of the editor and add editor-specific buttons (side='right') into `button_bar`."""
    frame = ttk.Frame(parent)
    # insert the text BEFORE going readonly (and avoid a StringVar, which would be GC'd after we
    # return - blanking the Entry). The Entry stays selectable/copyable in the readonly state.
    entry = ttk.Entry(frame, font=("TkDefaultFont", 9))
    entry.insert(0, os.path.abspath(path))
    entry.configure(state="readonly")
    entry.pack(side="top", fill="x", padx=6, pady=(6, 2))
    entry.xview_moveto(1.0)                                # show the tail (filename) of a long path

    bar = ttk.Frame(frame)
    bar.pack(side="top", fill="x", padx=6, pady=(0, 4))

    def _open_folder():
        _ok, msg = extedit.reveal(path)
        on_status(msg)

    ttk.Button(bar, text="Open folder", command=_open_folder).pack(side="left")
    return frame, bar
