"""The Documents tab: the input-document file pickers in TWO SECTIONS - the CURRENT documents
(I/O List + C&E Matrix, what the pipeline builds from) and the PREVIOUS revision (what the ph100
before/after quality report compares against). Each row has a Browse… picker and a Clear button; a
change is persisted IMMEDIATELY to the active project_params.yaml (round-tripping its comments, via
`config.save_document_path`). View-only of the active project's config - it follows a project switch
(`refresh()`).
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog

from pipeline4.core import config, i18n

# the two sections: (section i18n key, ((params key, row i18n label key), ...))
_SECTIONS = (
    ("doc_sec_current", (("iolist_path", "doc_iolist"),
                         ("matrix_path", "doc_matrix"))),
    ("doc_sec_previous", (("iolist_previous_path", "doc_iolist_prev"),
                          ("matrix_previous_path", "doc_matrix_prev"))),
)
_ROWS = tuple((key, label) for _sec, rows in _SECTIONS for key, label in rows)
_FILETYPES = (("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*"))


class DocumentsPanel(ttk.Frame):
    def __init__(self, parent, lang="en", on_status=lambda *_a: None):
        super().__init__(parent)
        self.lang = lang
        self.on_status = on_status
        self._rows: dict = {}             # key -> {"label", "entry", "browse", "clear"}
        self._sections: dict = {}         # section i18n key -> its ttk.Labelframe

        self._intro = ttk.Label(self, text="", wraplength=720, padding=(12, 12, 12, 8))
        self._intro.pack(side="top", anchor="w", fill="x")

        for section_key, rows in _SECTIONS:
            box = ttk.Labelframe(self, text="", padding=(10, 6, 10, 8))
            box.pack(side="top", fill="x", padx=12, pady=(0, 10))
            box.columnconfigure(1, weight=1)
            self._sections[section_key] = box
            for r, (key, _label_key) in enumerate(rows):
                label = ttk.Label(box, text="")
                label.grid(row=r, column=0, sticky="w", padx=(0, 10), pady=5)
                entry = ttk.Entry(box)
                entry.grid(row=r, column=1, sticky="ew", pady=5)
                entry.configure(state="readonly")
                browse = ttk.Button(box, text="", width=11,
                                    command=lambda k=key: self._browse(k))
                browse.grid(row=r, column=2, sticky="w", padx=(8, 4), pady=5)
                clear = ttk.Button(box, text="", width=9, command=lambda k=key: self._clear(k))
                clear.grid(row=r, column=3, sticky="w", pady=5)
                self._rows[key] = {"label": label, "entry": entry, "browse": browse, "clear": clear}

        self.set_lang(lang)
        self.refresh()

    # --- state ---------------------------------------------------------------------------------- #
    def refresh(self) -> None:
        """Reload all 4 paths from the active project_params.yaml (on construction + a project switch)."""
        paths = config.load_document_paths()
        for key, widgets in self._rows.items():
            self._show(widgets["entry"], paths.get(key, ""))

    def _show(self, entry: ttk.Entry, value: str) -> None:
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value or i18n.tr("doc_not_set", self.lang))
        entry.configure(state="readonly")
        entry.xview_moveto(1.0)                       # show the tail (the filename) of a long path

    def _label_for(self, key: str) -> str:
        return i18n.tr(dict(_ROWS)[key], self.lang)

    # --- actions -------------------------------------------------------------------------------- #
    def _browse(self, key: str) -> None:
        current = config.load_document_paths().get(key, "")
        initial = os.path.dirname(current) if current and os.path.isdir(os.path.dirname(current)) \
            else (config.active_project() or os.getcwd())
        chosen = filedialog.askopenfilename(parent=self, title=i18n.tr("doc_picker_title", self.lang),
                                            initialdir=initial, filetypes=_FILETYPES)
        if not chosen:                                # the user cancelled
            return
        config.save_document_path(key, chosen)
        self.refresh()
        self.on_status(i18n.tr("doc_set", self.lang, doc=self._label_for(key)))

    def _clear(self, key: str) -> None:
        config.save_document_path(key, "")
        self.refresh()
        self.on_status(i18n.tr("doc_cleared", self.lang, doc=self._label_for(key)))

    # --- chrome --------------------------------------------------------------------------------- #
    def set_lang(self, lang: str) -> None:
        self.lang = lang
        self._intro.configure(text=i18n.tr("doc_intro", lang))
        for section_key, box in self._sections.items():
            box.configure(text=i18n.tr(section_key, lang))
        for key, widgets in self._rows.items():
            widgets["label"].configure(text=self._label_for(key))
            widgets["browse"].configure(text=i18n.tr("doc_browse", lang))
            widgets["clear"].configure(text=i18n.tr("doc_clear", lang))
        self.refresh()                                # the (not set) placeholder is localized too

    def set_theme(self, _mode: str) -> None:
        """The Documents tab is all ttk (it follows the token styles automatically) - nothing classic-tk to re-theme."""
